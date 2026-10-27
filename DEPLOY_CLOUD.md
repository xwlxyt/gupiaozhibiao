# 云端部署：电脑关机也能自动更新 + 手机收推送

本地看板依赖这台电脑跑服务，关机就断。下面这套把它搬到 GitHub 的免费服务器上：
每个交易日 **北京时间 16:40** 自动抓取 → 计算 → 推送到手机 → 更新网页，你的电脑完全不用开机。

```
GitHub 定时器  ──►  抓取沪深全部A股日线  ──►  写回数据文件（仓库里）  ──►  Bark / 微信推送
                                        └──►  生成静态看板（GitHub Pages，手机可看）
```

---

## 当前进度（2026-10-27 更新）

仓库已是 <https://github.com/xwlxyt/gupiaozhibiao>，代码、2014 年至今全部数据、定时任务都已推送完成。

| 步骤 | 状态 | 说明 |
|---|---|---|
| 建仓库 + 贴 SSH 公钥 | ✅ 已完成 | SSH 认证通过（账号 `xwlxyt`） |
| 推送代码与数据 | ✅ 已完成 | 30 个文件，含 `data/breadth.db`、`docs/`、`.github/workflows/` |
| 定时任务注册 | ✅ 已完成 | Actions 里可见「A股宽度 每日更新与推送」，状态 active |
| **验证云端能访问行情接口** | ✅ 已完成 | 实测 GitHub 服务器出口 IP 132.196.15.178 访问腾讯日线接口返回 **HTTP 200**，取到真实行情 |
| **填推送密钥** | ⬜ 待你做 | 见下方「第 4 步」，只需 1 分钟 |
| **开启手机网页看板** | ⬜ 可选 | 见下方「第 6 步」 |

> 结论：**云端方案在这台机器上是可行的**。腾讯行情接口对 GitHub 的境外服务器完全开放，
> 速度比本机还快（单次请求约 0.5~1 秒）。下面第 1、2、3 步已不必再做，保留备查。

---

## 第 1 步：选一个推送渠道，拿到密钥（3 分钟）

任选其一即可，两者都配也行（会同时推）。

### 方式 A：Bark（iPhone，最省事）

1. App Store 搜索 **Bark** 并安装；
2. 打开 App，首页会显示一个形如 `https://api.day.app/AbCdEf123456/` 的地址；
3. 其中 `AbCdEf123456` 就是你的 **BARK_KEY**，先记下来；
4. 点 App 里的"测试"确认能收到通知。

### 方式 B：微信推送（Server酱 或 PushPlus）

- **Server酱**：浏览器打开 <https://sct.ftqq.com>，微信扫码登录 → 复制 **SendKey**（`SCT` 开头）。
- **PushPlus**：打开 <https://www.pushplus.plus>，微信扫码登录 → 复制 **token**。

---

## 第 2 步：建一个 GitHub 仓库（2 分钟）

1. 登录 <https://github.com>，右上角 **+** → **New repository**；
2. Repository name 随便起，例如 `astock-breadth`；
3. 可见性建议选 **Public**（免费账号只有公开仓库能开网页看板；不想公开就选 Private，推送照常，只是没有网页）；
4. **不要**勾选 "Add a README file" 等初始化选项，直接 **Create repository**；
5. 复制页面上显示的仓库地址，形如 `https://github.com/你的用户名/astock-breadth.git`。

---

## 第 3 步：把代码推上去（本机执行一次）

> 已经提交好了首版代码和 2014 年至今的全部历史数据，不需要重新回补。

### 3.1 先确认一件事：这台电脑没有独立安装 Git

实测本机 `PATH` 里没有 Git，`git` 命令只在 WorkBuddy 自带的 PortableGit 里存在。
所以如果你自己打开 cmd / PowerShell 敲 `git`，会提示"不是内部或外部命令"。两条路：

- **省事**：直接在对话里说"帮我推到 GitHub"，助手用内置 Git 执行（推荐）；
- **自己来**：先装 [Git for Windows](https://git-scm.com/download/win)，装完右键文件夹 → **Open Git Bash here**。

### 3.2 选通道：SSH 还是 HTTPS

实测结果（同一台机器）：

| 通道 | 连通性 | 认证方式 |
|---|---|---|
| `https://github.com/...` | **被拦（CONNECT 502）** | 弹窗登录 / PAT |
| `git@github.com:22` | ✅ 通 | SSH 密钥 |
| `ssh.github.com:443` | ✅ 通 | SSH 密钥 |

**结论：用 SSH。** 本机已生成好密钥（`C:\Users\wei\.ssh\id_ed25519`），
你只需要把下面这行公钥贴到 GitHub：

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFbROdPMKkwNbckc+wQgOJC3uKzhMV92p1o5MemlHr1g astock-breadth@workbuddy
```

粘贴位置：GitHub 右上角头像 → **Settings** → 左侧 **SSH and GPG keys** → **New SSH key**
→ Title 随便写（例如 `我的电脑`）→ Key 粘贴上面那行 → **Add SSH key**。

### 3.3 复制仓库地址

建好仓库后，仓库页面点绿色 **Code** 按钮 → 选 **SSH** 标签 → 复制，形如：

```
git@github.com:你的用户名/astock-breadth.git
```

### 3.4 三条命令

在 `astock-breadth` 文件夹里执行（地址换成你自己的）：

```bash
git remote add origin git@github.com:你的用户名/astock-breadth.git   # 关联远端
git branch -M main                                                  # 分支 master → main
git push -u origin main                                             # 推送并记住上游
```

- 第一条只做一次；`-u` 的意思是以后直接 `git push` 就行。
- 推送内容约 3.5 MB（代码 + 2014 年至今全部历史数据 + 静态看板），几十秒完成。
- 如果报 `Permission denied (publickey)`，说明公钥还没加、或加到了别的账号上。

### 3.5 验证推成功了

刷新仓库页面，应该看到：

- 首页自动显示 `README.md` 的中文说明；
- 文件列表里有 `data/`、`docs/`、`web/`、`.github/` 等，共 29 个文件；
- 顶部 **Actions** 标签里出现一条叫「A股宽度 每日更新与推送」的 workflow（此时还没运行）。

### 3.6 常见报错对照

| 报错 | 原因 | 处理 |
|---|---|---|
| `remote origin already exists` | 之前配过远端 | `git remote set-url origin git@github.com:你的用户名/仓库名.git` |
| `Permission denied (publickey)` | 公钥没加到 GitHub，或加错账号 | 重新复制 3.2 那行公钥，确认加到当前登录的账号下 |
| `Repository not found` | 地址拼错，或仓库是别人的 | 回仓库页面重新复制地址 |
| `CONNECT tunnel failed, response 502` | 走了 HTTPS 且被网络拦截 | 换成 `git@github.com:` 开头的 SSH 地址 |
| `src refspec main does not match any` | 分支改名没执行 | 先 `git branch -M main` 再 push |
| `failed to push some refs` / `non-fast-forward` | 远端已有内容（建仓库时勾了 README） | 建仓库时不要勾初始化；已勾的话先 `git pull --rebase origin main` |

### 3.7 可选：把提交作者改成你自己

当前两次提交的作者是占位值 `wei <wei@localhost>`，推到 GitHub 后不会关联你的头像。
在意的话在推送**之前**执行（换成你的 GitHub 用户名和邮箱）：

```bash
git config user.name "你的名字"
git config user.email "你的GitHub邮箱"
git rebase --root --exec "git commit --amend --reset-author --no-edit"   # 重写全部提交的作者
```

然后再执行 3.4 的推送。如果已经推过了，末尾加 `--force` 重推一次
（只有在没别人克隆这个仓库时才能这么做，现在正是这个时机）。

---

## 第 4 步：配置密钥（1 分钟）

在仓库页面：**Settings** → 左侧 **Secrets and variables** → **Actions** → **New repository secret**。

按你选的方式添加（名字必须完全一致）：

| Name | Value |
|---|---|
| `BARK_KEY` | 第 1 步拿到的 key（只填 key，不要带网址） |
| `SERVERCHAN_KEY` | Server酱的 SendKey |
| `PUSHPLUS_TOKEN` | PushPlus 的 token |

只需填你实际用的那一个（或多个）。

---

## 第 5 步：手动跑一次，验证真能抓取和推送

仓库页面 → **Actions** 标签 → 左侧 **A股宽度 每日更新与推送** → 右侧 **Run workflow** → 绿色按钮。

约 10 分钟后看结果（已实测：全量抓取 5224 只股票耗时 **613 秒**，0 只失败）：

- 点进这次运行，**Summary** 里会显示当天的简报；
- 手机应收到推送；
- 如果失败，看日志里哪一步红的：
  - 推送步骤显示"⚠️ 未配置推送通道" → Secrets 名字写错了，对照第 4 步检查大小写；
  - 报网络错误 → 基本不会发生，已实测 GitHub 境外节点访问腾讯行情接口返回 200。真遇到再找我。

> 当天数据已经更新过的话，会输出"今日无需更新，未推送"，这是正常的。
> 想强制测一次推送，把 `.github/workflows/daily.yml` 里那行改成 `python cloud_job.py --force`，提交一次，测完再改回来。

---

## 第 6 步（可选）：开启手机网页看板

仓库 **Settings** → 左侧 **Pages** → **Source** 选 **Deploy from a branch** → Branch 选 **main**、目录选 **/docs** → **Save**。

等 1~2 分钟，访问：

```
https://你的用户名.github.io/astock-breadth/
```

手机浏览器打开后可以"添加到主屏幕"，效果和本地看板一样（图表、单日查询、区间筛选、导出 CSV 全都有，只是"更新数据"按钮会隐藏）。

---

## 之后每天会发生什么

| 时间 | 动作 |
|---|---|
| 周一~周五 16:40（北京时间） | GitHub 自动运行：抓取 → 计算 → 推送 → 提交数据 → 更新网页 |
| 非交易日 / 节假日 | 脚本发现数据已是最新，直接跳过，不打扰你 |
| 某天漏跑（GitHub 偶尔延迟） | 下次运行会回看 30 个交易日自动补齐，不需要人工干预 |

想改时间：编辑 `.github/workflows/daily.yml` 里的 `cron: "40 8 * * 1-5"`（UTC 时间 = 北京时间减 8 小时）。

---

## 最后一步：停掉本机的定时任务

云端跑通后，本机 WorkBuddy 里那个 **16:30 的定时任务**就重复了，会让同一天收到两条推送。
直接跟我说"把本地那个定时任务停掉"，我来处理。

---

## 常见问题

**Q：数据会一直增长撑爆仓库吗？**
不会。每天只多一行，一年约 250 行，十几年下来数据文件也就几 MB。

**Q：Private 仓库能用吗？**
能，但免费账号的私人仓库开不了 Pages 网页，手机上只能看推送。Actions 额度每月 2000 分钟，这个任务每月约 220 分钟，够用。

**Q：GitHub 会不会哪天取消免费 Actions？**
有可能。代码是纯标准库、单文件脚本，随时可以搬到国内云函数或任意一台服务器上，只需要 `python cloud_job.py` 一条命令。

**Q：本地看板还要留着吗？**
建议留。历史数据、导出 CSV、离线查看都方便，只是不再指望它做日常更新。
