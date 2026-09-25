"""HTTP transport for the documented Agnes videos API. The key stays in the request header."""
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse


class AgnesHttpTransport:
    def __init__(self, base_url=None, timeout_s=600, interval_s=2):
        self.base = (base_url or os.environ.get('AGNES_BASE_URL') or 'https://apihub.agnes-ai.com/v1').rstrip('/')
        self.timeout_s = timeout_s
        self.interval_s = interval_s

    def fetch(self, url):
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read()

    def _request(self, url, key, data=None):
        headers = {'Authorization': 'Bearer ' + key}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors='replace')[:500]
            raise ValueError('Agnes HTTP ' + str(exc.code) + ': ' + detail) from None

    def submit(self, payload, key):
        result = self._request(self.base + '/videos', key, payload)
        video_id = result.get('video_id') or result.get('id')
        if not video_id:
            raise ValueError('Agnes submit response has no video id')
        return video_id

    def poll(self, task_id, key, model=None):
        origin = self.base[:-3] if self.base.endswith('/v1') else self.base
        deadline = time.time() + self.timeout_s
        last = None
        delay = self.interval_s
        while time.time() < deadline:
            query = {'video_id': task_id}
            if model:
                query['model_name'] = model
            try:
                last = self._request(origin + '/agnesapi?' + urlencode(query), key)
            except ValueError as exc:
                if 'HTTP 429' not in str(exc):
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            delay = self.interval_s
            status = last.get('status')
            if status == 'completed' and last.get('url'):
                return last['url']
            if status == 'failed':
                raise ValueError('Agnes task failed: ' + str(last.get('error')))
            time.sleep(self.interval_s)
        raise TimeoutError('Agnes task did not complete; last status ' + str((last or {}).get('status')))

    def download(self, remote, dest):
        parsed = urlparse(remote)
        if parsed.scheme not in ('https', 'http'):
            raise ValueError('Refusing non-http video URL')
        data = self.fetch(remote)
        dest = os.fspath(dest)
        os.makedirs(os.path.dirname(dest) or '.', exist_ok=True)
        with open(dest, 'wb') as handle:
            handle.write(data)

    def probe(self, dest):
        from ..assembly import _probe
        return _probe(dest)
