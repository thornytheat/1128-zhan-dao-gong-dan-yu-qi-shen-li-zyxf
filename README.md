# 占道工单逾期审理

面向市政审理的本地工作台。内置业务样例覆盖市政占道工单逾期预测与许可复核排班。样例采用确定性构造，适合复现实验和核查边界行为。

## 启动

```sh
docker compose up --build -d
```

打开 `http://127.0.0.1:18207/` 查看占道许可台账。左侧六个入口可展开运行证据。调整「复核名额（单）」，点击「重新排班」比较处置结果。结束后执行 `docker compose down --remove-orphans`。

## 独立业务模块

- 许可流转 `permit_intake`
- 日历折算 `calendar_intervals`
- 审理特征 `review_features`
- 超期概率 `deadline_classifier`
- 审理编组 `review_roster`
- 许可追溯 `permit_journal`

## 查看运行结果

- `GET /api/overview` 返回默认运行及其指纹。
- `POST /api/scenario` 接收 `{"capacity": 3}`。入口接受 1–100 的整数，应用样例时使用该业务额度。
- `GET /api/stages/permit_journal` 查看该环节的独立证据，支持 `?capacity=3`。

```sh
docker compose exec -T app python -m permitdesk.delivery evaluate --capacity 3
docker compose exec -T app pytest -q
```

数据和模型约定见 [业务契约](docs/SPEC.md)。模块、例外规则与验证入口见 [业务深度](docs/DEPTH.md)。
