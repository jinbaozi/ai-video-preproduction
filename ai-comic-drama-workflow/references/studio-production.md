# V2.0 studio 制作手册

新 `start` 默认使用 studio：单宿主、原生产物、按镜头制作。普通创作自主完成。先写出对白并量真实时长，再做最少参考和五镜试制，通过后批量。无需八个常驻 Agent 或新的协调 CLI。

## 0.20.2 图片阶段门禁

新 studio 另启用 [执行门禁与图片终点](execution-gates.md)。先图片时使用 `--stop-after images` 或原生 `scope`，不跳过编剧、导演、美术；生图先 `begin-image`，结果绑定原记录，实际视觉检查逐项提交。UNKNOWN 只能凭结构化原任务证据回收。成功图片交付状态为 `IMAGES_DELIVERED`，不等于视频前期或成片完成。

## 基础入口

```sh
ai-comic-drama start '<简报或源文件>' --project ./episode --production-target video --target '<真实目标>'
ai-comic-drama step ./episode --result '<实际原生结果.json>'
```

用户不填 JSON。宿主读取当前 `context`，提交 core-result，程序生成哈希和校验回执。每阶段只读必要原生输入，不重复读完整信封。studio 默认自动选择专业方法和适用人物；宿主提交来源绑定的 craft_context 与实际 craft_review。只精简重复展示，不取消选择和采用证据。原句、说话人、动机、身份、场景、道具、起止态与模型硬约束必须保留。

默认可直接用实际参考图，不强制 Flow 2K；默认通过内置 FFmpeg 编辑。只有用户要求或入口需要时，才显式开启 `--reference-refinement google-flow-2k` / `--editing-backend jianying-headless`。目标入口的真实最低规格不能省略。

旧配置用 `--profile lean`；独立审阅任务模式用 `--profile audited`。已有项目保持原配置，不自动迁移。`--delivery full` 保留真实图像需求；缺媒体不能改称 text-only 完成。

## 剧本、声音与镜头

统筹稿同时明确观看理由、此时新增信息和结尾悬念/未完成动作。90 秒《借灯》只是连续性夹具，不是所有平台默认规格。不写不必要的名家研究或美学九维合同。

1. ScriptIR 锁定对白与说话人。
2. 用真实可用且已授权的 TTS/录音生成临时声音。本工具不生成 TTS，不做声纹授权或转写判断。
3. 宿主按实际 ScriptIR 建立 JSON 指针绑定。以下是字段示例，指针必须根据真实文件调整，不可复制成虚假引用：

```json
[
  {"shot_id":"S005","text_pointer":"/lines/0/text","speaker_pointer":"/lines/0/speaker","audio_file":"/absolute/voice-1.wav","slot_ms":9000},
  {"shot_id":"S005","text_pointer":"/lines/1/text","speaker_pointer":"/lines/1/speaker","audio_file":"/absolute/voice-2.wav","slot_ms":9000}
]
```

```sh
ai-comic-drama production ./episode measure-dialogue \
  --script /absolute/ScriptIR.json --bindings /absolute/dialogue-bindings.json --margin-ms 200
```

程序解码音频并实测时长。顺序对白按同镜相加，每句加停顿余量。`FITS` 只说明时间容得下，不说明台词正确、声音授权或口型通过。`SPLIT_REQUIRED` 返回码 2，由拥有者拆镜/重规划；禁止自动缩短原句或拉伸音频。重叠对白应拆成真实分轨并在原生声音方案处理，本简单检查不假设它可同时播放。

## 生产计划与预算一次准备

先用既有 `production plan` 建立冻结 job；用 `freeze` 确定全片原生镜头范围、硬检查、画幅和时间范围。这个版本不跳过原生前期就直接宣称正式生产通过。可以先用独立专业技能探索风险，完整项目只需先完成足以编译的镜头骨架，生成顺序仍先风险镜头。

在**第一次视频执行前**调用 `studio-configure --file <配置>`。新 studio 项目由程序强制检查；旧项目只在没有执行记录时可显式选择，禁止自动迁移已有费用。示例中金额仅演示字段，不是已授权费用或市场报价：

```json
{
  "currency":"CNY",
  "cap_minor":10000,
  "max_total_attempts":12,
  "authorization_file":"/absolute/actual-authorization.txt",
  "quotes":{"JOB_actual_1":1000,"JOB_actual_2":1000},
  "canary":{
    "prop_closeup":"S003",
    "two_speakers":"S005",
    "handoff":"S011",
    "single_closeup":"S008",
    "camera_motion":"S002"
  }
}
```

`quotes` 要列齐将执行的真实 job ID，每项是**每次尝试的费用上界**；不知道上界就先查实际价格，不能填零假装免费。金额以所选币种的最小单位计，不混币种、不用浮点数。CNY 的 100 表示 1 元。零仅用于已确认免费的路径。五镜以上逐项覆盖五种风险：适用项绑定真实试镜，不适用项通过 risk_exclusions 记录原因、完整镜头范围和证据文件；同一镜头可验证多个适用风险。不足五镜时试制覆盖全部实际镜头。不得为凑类别增加双人或交接剧情。

对白戏配置还应附可选字段，内容由宿主根据实际音频整理：

```json
{"dialogue":{"script_file":"/absolute/ScriptIR.json","bindings":[],"margin_ms":200}}
```

这里的空 `bindings` 是占位说明，实际有对白时不能留空，否则配置被拒绝。配置会重新量时长并绑定逐句文本、说话人和音频哈希。每次提交只复核该 job 涉及的绑定；变更其他句子不使当前句失效。宿主必须确保所有需要对白的镜头都进入绑定；程序不从自由格式全剧本推断覆盖率。

```sh
ai-comic-drama production ./episode studio-configure --file /absolute/studio-config.json
ai-comic-drama production ./episode studio-report
```

配置与授权文件哈希绑定且不可覆盖。授权文件是当前可信宿主保存的实际会话/批准来源，不是模型自行写一句“已批准”。本地项目目录是可信存储，不是防恶意宿主的身份认证服务。

预算覆盖本台账的视频尝试，不自动包含外部 TTS、图像、订阅费或人工费；这些另记实际账单，不能把此报表称作全项目总成本。

## 真实执行和 UNKNOWN 恢复

已支持的 API 路径继续 `production execute --job ... --out ...`。外部网页/本地模型入口在生成前预留：

```sh
ai-comic-drama production ./episode begin-external --job JOB_actual
```

返回原生 `EXE_...`，宿主保存，然后才调用当前已授权的实际工具。程序不提供伪造的通用生成 API。提交不明时不要再次 begin；保留原 record，查原任务/历史/账单。

`reconcile` 的证据文件由宿主根据真实查询结果制作：

```json
{
  "record_id":"EXE_actual",
  "payload_sha256":"从原生job读取，不由模型手填猜测",
  "state":"SUBMITTED",
  "task_id":"真实厂商任务ID",
  "proof_file":"/absolute/provider-history.json",
  "observation":"查询到了原提交任务，记录中任务ID与参数匹配。"
}
```

```sh
ai-comic-drama production ./episode reconcile --record EXE_actual --evidence /absolute/reconcile.json
ai-comic-drama production ./episode receive-take --job JOB_actual --record EXE_actual \
  --file /absolute/downloaded.mp4 --probe /absolute/observed-probe.json
```

probe 可用 `{}`，严格项目仍由程序实测，不能靠声明跳过探测。`SUBMITTED` 只表示已经找回厂商任务，媒体尚未验收。明确终态失败可对账为 `FAILED`；观察必须说明真实失败证据。没有 task ID 且确认未提交时可用 null，但超时、按钮消失、取消请求不等于明确失败。

自动 API 已有任务 ID 则使用既有 `recover-execution --record ... --out ...` 下载原任务。新证据绑定错误 payload/task、空文件、已结束任务冲突都拒绝。更换 request/job ID 仍不能绕过重叠镜头的未决执行。

## 适用风险放行与结算

先按原生 `review-take` 和 `select` 接受风险镜头；检查项至少覆盖身份、服装、道具左右手/交接、说话人和口型、缺文件。没有实际看见/听见，不提交 PASS。程序只复核证据链与字节，不替代视觉判断。

`studio-report.canary` 读取原生选择与审阅，不单独保存另一套 PASS。试镜没齐或媒体被改动，批量提交失败。少于五镜的小项目全片作为试制，不要求为了凑数制造无关镜头。

厂商任务终态后持真实账单结算：

```sh
ai-comic-drama production ./episode settle --record EXE_actual \
  --amount-minor 800 --receipt /absolute/actual-bill.json
```

UNKNOWN/SUBMITTED/SUBMITTING 保留全部预留。已失败但没账单也保留。相同结算重放幂等；金额冲突不覆盖旧账。真实超额账单照实记录并阻止新花费。已接受秒数来自唯一选择的镜头时间范围，不累计废片和重复生成；分母为零时单价为 null。存在未结算项时，已结算单位成本尚非最终成本。

## 剪辑、修复与交付

继续原生 `assemble / review-sequence / deliver`，不增加第二份时间线。FFmpeg 输出、便携 JSON 与剪映原生草稿区分标记。`VIDEO_DELIVERED` 需要原生所有门通过；`DELIVERED` 只是前期完成。

生成失败不重写剧本；对白变更只定位依赖句子及镜头，必要接点重审；字幕错字不重生成 Take。使用原生 `revise` 与 `copy-project` 保留旧版。当前冻结生产 policy/manifest 没有任意自动重基接口，已经锁定的故事变更需显式重规划对应生产范围，不能直接篡改已接受记录。

缺账号、实际媒体、视频观看/音频能力、上界报价或授权时保留具体阻塞。只交已完成产物及原任务恢复入口；不造 TTS、真实生成、商业许可或发布成功证明。
