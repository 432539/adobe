# 完整源码（须授权拉取）

公开仓库 `432539/adobe` **不含**完整实现。

完整版在私有仓库：**https://github.com/432539/ad-xiaoguai**（未授权打开是 404）。

## 怎么开通

1. **给公开仓库点 Star**（`432539/adobe`）。`scripts/star_grant.py` 每约 10 分钟扫一次，自动邀请进私有仓（个人仓只能给写权限）。  
2. 或加 QQ 群 **19302577**，报 GitHub 用户名，由群主手动邀请。  
3. 到 GitHub 通知 / 邮箱接受 Collaborator 邀请。  
4. 拉取：

```bash
git clone https://github.com/432539/ad-xiaoguai.git
```

未授权不得转载或二次分发。点 Star 即视为申请完整源码，请只给可信开发者用这条通道。

## 群主本机 / Actions

```bash
# 经典 PAT：勾选 repo。写入环境变量，不要提交。
set STAR_GRANT_TOKEN=ghp_...
python scripts/star_grant.py --once    # 跑一轮
python scripts/star_grant.py --watch   # 本机常驻
```

GitHub Actions：公开仓库 Settings → Secrets → `STAR_GRANT_TOKEN`，工作流 `.github/workflows/star-grant.yml` 每 10 分钟跑一次。

## 公开仓库没有的部分
- `frontend/` 整目录
- `harvester/` 整目录
- AD 出图 / 换票 / 请求体 / worker / 号池 / ARP 存取
- `docs/02-arp-core.md`、`docs/12-minting-and-config.md`、`docs/13-models.md`
