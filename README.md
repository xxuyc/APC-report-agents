# APC Report Agents

两个面向污水处理项目的报告 Agent：

- `generate-survey-report`：从现场调研 Excel 和补充材料生成可追溯的现状评估。
- `generate-operation-analysis-report`：从生产运营 Excel 生成运营分析报告、图表和审核工作簿。

`knowledge_center` 是两者共用的可选知识中心。默认完全本地运行；只有用户显式
启用时才通过本机 `lark-cli` 连接公司飞书 Base。

本仓库包含内部项目标识，只能放在私有 GitHub 仓库并授权给获批人员。

## 环境

- Windows 10/11 或 macOS
- Python 3.10 及以上
- WorkBuddy
- 不要求 Microsoft Office、Node.js 或 Codex 内置运行时

## 用户级安装

先克隆私有仓库，然后执行当前平台的安装脚本。脚本创建项目虚拟环境，并把整个
仓库链接到用户级 `~/.workbuddy/skills/APC-report-agents`，两个 skill 因此
在所有 WorkBuddy 项目中可发现，同时继续共享同一份 `knowledge_center`。

Windows PowerShell：

```powershell
git clone https://github.com/xxuyc/APC-report-agents.git
cd APC-report-agents
.\install.ps1
```

macOS：

```bash
git clone https://github.com/xxuyc/APC-report-agents.git
cd APC-report-agents
chmod +x install.sh
./install.sh
```

需要运行飞书长连接监听器时，安装脚本增加 `--knowledge`（macOS）或
`-Knowledge`（Windows）；普通知识检索和写回使用本机 `lark-cli`，无需该
可选 Python 包。

## 知识中心选择

`prepare` 的 `--knowledge-mode` 支持：

- `disabled`：默认值；不读取飞书配置，不访问网络，不写回。
- `optional`：尝试连接；失败后继续本地报告流程并记录警告。
- `required`：知识检索或 QA 后写回失败时停止。

本地模式应显式提供 `--project-id`。真实配置从
`knowledge_center/feishu-connection.example.json` 复制为被 Git 忽略的
`feishu-connection.local.json`；禁止把 App Secret 或机器人凭据写入仓库。

## 验证

```text
python scripts/verify_release.py
python -m unittest discover -s knowledge_center/tests -t . -v
python generate-survey-report/tests/smoke_test_pipeline.py
python generate-operation-analysis-report/tests/smoke_test_pipeline.py
```

Skill 结构校验还需要 `requirements-dev.txt`。
GitHub Actions 会在 Windows 和 macOS 上重复执行发布检查与全部测试。

详细发布边界见 `RELEASE.md`。
