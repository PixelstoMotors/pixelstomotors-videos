# pixelstomotors-videos

[Pixels to Motors](https://adaptdesign.jp/pixelstomotors) のサイトの「Video | 解説動画」スライダーが読む、YouTube 本編の一覧を置くリポジトリです。

- `site/youtube/videos.json` … スライダーが読む一覧（新しい順・本編だけ・最大10本）。手で直さない
- `site/youtube/build_videos_json.py` … チャンネル（@PixelstoMotors）の RSS から一覧を作り直すプログラム。API キーは使わない
- `site/youtube/overrides.json` … タグの決め方と、動画ごとの上書き（`videos` に動画IDごとの `tag` / `title` / `description` / `hide`）
- `.github/workflows/youtube-videos.yml` … 6 時間ごとに一覧を作り直し、変わったときだけ commit する。Actions の画面から手動でも動かせる

スライダーは `https://raw.githubusercontent.com/PixelstoMotors/pixelstomotors-videos/main/site/youtube/videos.json` を読みます。

## 一覧から外したい動画があるとき

`overrides.json` の `videos` に次のように書いて commit する。次の更新で一覧から消える。

```json
"videos": {
  "動画ID": { "hide": true }
}
```
