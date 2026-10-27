# 云端部署：电脑关机也能自动更新 + 手机收推送

本地看板依赖这台电脑跑服务，关机就断。下面这套把它搬到 GitHub 的免费服务器上：
每个交易日 **北京时间 16:40** 自动抓取 → 计算 → 推送到手机 → 更新网页，你的电脑完全不用开机。

```
GitHub 定时器  ──►  抓取沪深全部A股日线  ──►  写回数据文件（仓库里）  ──►  Bark / 微信推送
                                        └──►  生成静态看板（GitHub Pages，手机可看）
```

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

在这个文件夹（`astock-breadth`）里打开命令行，执行（把地址换成你自己的）：

```bash
git remote add origin https://github.com/你的用户名/astock-breadth.git
git branch -M main
git push -u origin main
```

首次推送会弹出 GitHub 登录窗口，按提示授权即可。

> 已经提交好了首版代码和 2014 年至今的全部历史数据，不需要重新回补。

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

约 5~10 分钟后看结果：

- 点进这次运行，**Summary** 里会显示当天的简报；
- 手机应收到推送；
- 如果失败，看日志里哪一步红的：
  - `更新数据并推送` 报网络错误 → 说明 GitHub 服务器访问腾讯行情接口受限，告诉我，改用国内云函数方案；
  - 推送步骤显示"⚠️ 未配置推送通道" → Secrets 名字写错了。

> 当天已经更新过的话，会输出"今日无需更新，未推送"，这是正常的。想强制测一次推送，把 `cloud_job.py` 那步改成 `python cloud_job.py --force` 临时提交一次即可。

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
