# 私有仓库发布规则

本仓库仅供获批内部人员使用。当前参考资料保留城南、东阳、兴化等内部项目标识，
不得公开、转发或改为公开仓库。

## 允许发布

- `knowledge_center/`
- `generate-operation-analysis-report/`
- `generate-survey-report/`
- 根目录的安装、依赖、测试、发布说明和架构图

## 禁止发布

- `knowledge_center/feishu-connection.local.json`、`.env`、密钥和访问令牌
- 原始项目 Excel、PDF、DOCX、图片及人工审核成果
- `survey-report-workspace/`、`operation-analysis-workspace/`、`runs/` 和输出文件
- 虚拟环境、依赖目录、缓存、日志、Office 锁文件和系统临时文件

可复用 Word 模板只能位于对应 skill 的 `assets/`。无真实凭据的
`.env.example` 和 `feishu-connection.example.json` 必须保留。

## 发布检查

每次提交和推送前依次执行：

```text
python scripts/verify_release.py
python -m unittest discover -s knowledge_center/tests -t . -v
python generate-survey-report/tests/smoke_test_pipeline.py
python generate-operation-analysis-report/tests/smoke_test_pipeline.py
```

维护者运行 skill 结构校验前安装 `requirements-dev.txt`。
推送后必须等待 Windows 和 macOS 两个 GitHub Actions 作业通过。

检查通过后再按逻辑模块提交。默认分支为 `main`，远端仓库必须保持 private。
