# 飞书原位编辑与验收

先读当前环境提供的飞书相关技能（若有）与命令帮助。本文记录实际工作中有用的方法，不替代当前 CLI 的参数定义和权限流程。飞书导出是可选集成：仅在当前环境提供相应能力时使用。Windows 可优先使用 PATH 中的 `lark-cli.cmd`，其他系统使用 `lark-cli`；也可选用环境已经提供的飞书连接器。身份和权限按当前工具契约处理。没有飞书工具时仍可交付本地文件，不要假设本仓库自带登录或账户权限。

示例命令以 Windows 的 `lark-cli.cmd` 书写；其他系统按实际可执行文件名调整。

## 稳定读取与 UTF-8

```text
lark-cli.cmd docs +fetch --as user --doc DOC_TOKEN --detail full --jq "tojson | @base64"
```

Windows 转发大量中文 stdout 时曾出现分块编码损伤。加 jq 将整个 JSON 转成 base64，再在本地解码，可排除传输导致的 U+FFFD。先确认当前 CLI 的 jq 输出契约：此版本输出原始 base64 字符串，不是外层 JSON 对象。

Python 调用示例（先选择已确认存在的 CLI，参数用列表）：

```python
import base64, json, shutil, subprocess
cli = shutil.which("lark-cli.cmd") or shutil.which("lark-cli")
if not cli:
    raise RuntimeError("未找到宿主 CLI，请检查实际安装位置")
p = subprocess.run(
    [cli, "docs", "+fetch", "--as", "user", "--doc", doc_token,
     "--detail", "full", "--jq", "tojson | @base64"],
    capture_output=True, timeout=120,
)
if p.returncode:
    # 按共享技能检查授权/CLI 错误；不要原样打印可能含敏感值的原始响应。
    raise RuntimeError(f"读取失败，退出码 {p.returncode}")
response = json.loads(base64.b64decode(p.stdout.strip(), validate=True))
if response.get("ok") is not True:
    raise RuntimeError("CLI 未报告成功，需检查错误类型")
xml = response["data"]["document"]["content"]
```

原文出现乱码时先用这种方法回读；确认服务器内容真的损坏后才找音频修复，避免修复传输伪影。不要无条件禁掉日文、阿拉伯文等字符：多语言访谈可能合法出现这些文字。

中文/XML/多行内容写 UTF-8 文件，CLI 用 cwd 下相对 `@file`。避免把中文脚本经 PowerShell 管道输给 Python，宿主编码可能使字面量变成问号。不要在 shell 字符串中拼接标题、URL 或 XML。

## 成稿 XML 的关键形式

以下片段示范样式，不是完整成稿。`&`、`<` 等正文字符须用 XML 库或 html.escape 转义。

```xml
<h2>开篇简介</h2>
<p>节目、嘉宾与主题简介。</p>
<p><a href="https://www.xiaoyuzhoufm.com/episode/REPLACE_ID">小宇宙原节目</a></p>
<h2>嘉宾核心洞察</h2>
<callout emoji="💡" background-color="light-blue" border-color="blue"><ol>
  <li>有来源的洞察概括。</li>
</ol></callout>
<h2>全文文本</h2>
<h3>章节标题</h3>
<p><b><span text-color="blue">主持人姓名：完整的主持人发言。</span></b></p>
<p>嘉宾姓名：完整的嘉宾发言。</p>
```

回读时蓝色可能规范化为 `rgb(36,91,219)`。检查主持人段落全部文字的继承样式，不能只看到一个蓝色名字就判通过。

## 预检、写入和结果判断

先查看 `docs +script --help`、`docs +update --help` 和适用技能。曾使用的 CLI 预检形式（先核对当前帮助）：

```text
lark-cli.cmd docs +script --as user --command parse --content @./candidate.xml
```

检查 `ok=true` 及 `data.assessment.status=passed`；预检通过仅说明结构可解析。

读取最新 revision 和块 ID 后，受控替换范围的形式：

```text
lark-cli.cmd docs +update --as user --doc DOC_TOKEN --command block_replace --start-block-id FIRST_BLOCK --end-block-id LAST_BLOCK --revision-id REVISION --doc-format xml --content @./replacement.xml
```

检查 `ok=true`、`data.result=success`、warnings 为空。revision 变化时重新读取并核对差异。部分成功、超时或返回不明确时，先查实际服务器状态，再决定是否补写。

`<ul>` 等展示层容器有时没有块 ID，而子 `<li>` 的父级又不同。不能用无 ID 容器或跨父级节点作为替换范围端点；结构修改后旧 ID 不能继续复用。先缩小到有 ID 的合法块；整篇覆盖只在用户授权整篇重整且资源可保全时使用。

Wiki 标题需按当前 `lark-drive`/`lark-wiki` 帮助处理，正文标题变化不保证目录标题同步。不要通过新建一个独立云盘文档来冒充原 Wiki 已更新。

## 回读验收清单

1. 同一目标 token、Wiki 节点和父目录；没有遗漏图片、附件、表格和嵌入对象。
2. 标题元数据、期号、嘉宾身份与原节目相符；简介链接指向本期，且可点击。
3. 默认三个 H2、一个 callout 有序列表、3–6 个全文章节；用户另有要求则按其要求。
4. 主持人整段蓝色加粗，嘉宾普通黑色；全文角色和顺序经文字/音频检查。
5. 回读正文与候选逐块比较，忽略生成的 ID 和无语义缩进，不忽略词句、链接或样式差异。排版检查器通过不代表内容比对通过。
6. 核对正文中没有过程说明、未替换占位符、真实乱码或意外删除。

发送文件时读 `lark-im` 的 reply reference，通过 `im +messages-reply --as bot --message-id INCOMING_ID --file ./file.ext` 发真实附件。MP3 作为 `--file` 发送，`--audio` 是 Opus 语音消息。仅展示本地 Markdown 路径不等于已经给飞书用户发送文件。
