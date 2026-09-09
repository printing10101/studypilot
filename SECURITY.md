# Security Policy

## Supported Versions

仅最新 `main` 分支接收安全修复。

## Reporting a Vulnerability

请通过 GitHub Security Advisories（仓库页 → Security → Report a vulnerability）私信报告，勿在公开 Issue 中贴出可利用细节。

## Scope Notes

- 本项目为本地优先学习助手，默认监听本机；请勿将实例直接暴露到公网。
- `.env`、数据库、上传文件均在 `.gitignore` 中，勿提交密钥或真实学生数据。
- 依赖 LLM / 嵌入服务时，请使用本机或可信端点，并妥善保管 API Key。
