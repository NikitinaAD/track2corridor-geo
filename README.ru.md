# track2corridor-geo

Инструмент строит проверяемую центральную линию и коридор из упорядоченных точек
трека. Результат содержит исходный footprint, centerline, corridor и JSON с полной
диагностикой графа и растра.

```bash
track2corridor build track.laz --footprint-width 20 \
  --corridor-width 8 --output corridor.gpkg
```

Автоматического преобразования координат нет: вход должен иметь проекционную CRS
в метрах.

Copyright 2026 Alena Nikitina. Apache License 2.0.

