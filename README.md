# 特种设备安全码 PDF 生成器

一个面向特种设备使用单位的开源批量排版工具。上传二维码图片后，系统自动识别并提取20位设备安全码，生成可直接打印的规范尺寸 PDF。

在线体验：[https://safe.adeptmake.com/](https://safe.adeptmake.com/)

详细网页教程：[https://safe.adeptmake.com/guide](https://safe.adeptmake.com/guide)

详细操作方法、打印设置和故障排查请查看[使用说明](使用说明.md)。

## 主要功能

- 批量上传 PNG、JPG 或 WEBP 图片，单次最多200张
- 自动识别二维码链接中的20位 `code` 安全码
- 兼容纯二维码图片和带标题、编号的新版导出图片
- 自动精准裁切二维码区域，避免标题和编号重复
- 检查重复码、无效码和一张图片中的多个二维码
- 左竖排、右竖排两种模板
- 60×90、80×120、100×150 mm 三种物理尺寸
- 可选救援电话及安全码排序
- 每个安全码生成一页 PDF
- 图片仅在请求内存中临时处理，不写入服务器磁盘
- 响应式网页，支持电脑和手机使用
- 内置完整图文教程

## 技术栈

- FastAPI
- Pillow
- zxing-cpp
- ReportLab
- Docker / Docker Compose
- 原生 HTML、CSS 和 JavaScript

## 本地 Docker 运行

```powershell
docker compose up --build -d
```

Dockerfile 默认通过国内镜像源获取 Python 基础镜像。如服务器可直接访问 Docker Hub，可使用：

```bash
docker compose build --build-arg PYTHON_IMAGE=python:3.12-slim --build-arg DEBIAN_MIRROR=
docker compose up -d
```

浏览器访问：`http://localhost:8088`

查看状态：

```powershell
docker compose ps
docker compose logs -f
```

停止服务：

```powershell
docker compose down
```

## 目录结构

```text
app/
  main.py               Web API 与页面路由
  generator.py          二维码识别、裁切和 PDF 排版
  static/                前端页面与图文教程
deploy/                  Nginx 配置示例
docker-compose.yml       Docker Compose 配置
Dockerfile               应用镜像定义
```

## 服务器部署

将整个目录上传到安装了Docker的服务器，在目录内执行：

```bash
docker compose up --build -d
```

容器仅监听服务器本机的8088端口。Nginx配置示例位于 `deploy/`。

正式访问地址：`https://safe.adeptmake.com/`

域名独立站点配置位于`deploy/nginx-safe.adeptmake.com.conf`。服务器使用Let's Encrypt证书，并由现有Certbot定时器自动检查续期。

## 更新部署

在服务器项目目录执行：

```bash
cd /opt/safety-code-web
docker compose up --build -d
docker compose ps
curl -fsS http://127.0.0.1:8088/api/health
```

查看最近日志：

```bash
cd /opt/safety-code-web
docker compose logs --tail=200
```

## 隐私说明

上传的图片只在单次请求的内存中用于二维码识别和 PDF 生成，不会写入服务器磁盘。部署者仍应根据自己的运行环境配置 HTTPS、访问日志和数据安全策略。

## 参与贡献

欢迎通过 Issue 提交识别失败样本、排版建议或功能需求，也欢迎提交 Pull Request。请勿在 Issue 中上传包含账号、密码、手机号或其他敏感信息的截图。

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
