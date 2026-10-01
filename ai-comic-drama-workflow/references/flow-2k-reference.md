# Google Flow 2K 参考素材门

本合同只在 `delivery=full` 且图片会作为视频模型参考时启用。它不替代原始图片生成和看图审核，而是在图片审核通过后增加一层**保真 2K 参考素材**处理。

## 宿主职责

1. 使用 Google Flow 的当前可用图片编辑/生成入口，把已接受的 ReferenceImage / BoardImage 作为唯一视觉来源处理到 2K 级参考素材。
2. 需要登录时停止并通知用户。账号选择属于本地会话信息，不写入仓库、项目事实、日志或交付包。
3. 不允许把本地插值、简单 resize 或改扩展名伪装成 Flow 输出。
4. Flow 返回后必须重新观察实际图片。至少核对：人物身份、服装、姿态、构图、空间左右、关键道具、光色、画面文字、手脸结构。
5. 只有通过保真审核且长边 >= 2048 像素的真实文件才能进入视频模型附件映射。原始图片继续保留，Flow 输出是派生参考素材。
6. Flow 无法访问、需要登录、生成状态未知、文件未回收、分辨率不足或保真失败时，状态为 BLOCKED；不得绕过 2K 门直接投喂视频模型。

## 最小回执

宿主为每张派生图登记：

```json
{
  "schema_version": "flow-2k-reference/1.0",
  "source_sha256": "...",
  "output_sha256": "...",
  "output_uri": "...",
  "width": 2048,
  "height": 3072,
  "provider": "google-flow",
  "operation": "reference-preserving-2k",
  "visual_review": {
    "identity": "PASS",
    "wardrobe": "PASS",
    "pose_action": "PASS",
    "composition_space": "PASS",
    "props": "PASS",
    "lighting_color": "PASS",
    "text": "PASS"
  },
  "status": "ACCEPTED"
}
```

宽高只记录真实探测值，不强制固定比例。没有可见文字时 `text` 可为 `NOT_APPLICABLE`。

## 自动推进

通过后直接继续分镜或模型编译，不向用户请求定稿。只有真实阻塞才通知用户；登录、权限、付费授权、未知执行状态和无法自动修复的保真失败属于真实阻塞。
