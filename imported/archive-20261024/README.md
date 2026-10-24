# 控えから取り込んだ古い版（2026-10-24）

このフォルダには、履歴を作り直す前の非公開の控えにだけ残っていた中身を、消さずに残すために置いています。

- 置き方: `<控えの枝またはタグ>/<元のパス>`。中身は控えのままです（下の「伏せたもの」を除く）。
- ここにあるファイルは実行も読み込みもされません。テストの収集からも外しています。
- 今のコードへ採り入れるかは、ファイルごとに別のPRで決めます。
- 公開側の履歴に同じ中身があるもの、行がすべて公開側にあるもの、ほかの版で行がそろうものは入れていません。
- 意図して外されていたもの（個人の情報を含む、公開側で削除済みなど）は入れていません。

## 入れたファイル

| 元のパス | 控えの枝・タグ | 置き場所 | 備考 |
|---|---|---|---|
| `.github/workflows/ci.yml` | `ci/add-ci-workflow` | `ci/add-ci-workflow/.github/workflows/ci.yml` |  |
| `.github/workflows/preflight.yml` | `ci/add-preflight-gate` | `ci/add-preflight-gate/.github/workflows/preflight.yml` |  |
| `README.md` | `cursor/readme-posix-setup-a81c` | `cursor/readme-posix-setup-a81c/README.md` |  |
| `src/toc_engine/cli.py` | `cursor/readme-posix-setup-a81c` ほか2 | `cursor/readme-posix-setup-a81c/src/toc_engine/cli.py` |  |
| `src/toc_engine/dashboard.py` | `cursor/readme-posix-setup-a81c` ほか2 | `cursor/readme-posix-setup-a81c/src/toc_engine/dashboard.py` |  |
| `src/toc_engine/history.py` | `cursor/readme-posix-setup-a81c` ほか2 | `cursor/readme-posix-setup-a81c/src/toc_engine/history.py` |  |
| `src/toc_engine/report.py` | `cursor/readme-posix-setup-a81c` ほか2 | `cursor/readme-posix-setup-a81c/src/toc_engine/report.py` |  |
| `tests/test_constraint.py` | `cursor/readme-posix-setup-a81c` ほか2 | `cursor/readme-posix-setup-a81c/tests/test_constraint.py` |  |
| `tests/test_history.py` | `cursor/readme-posix-setup-a81c` ほか2 | `cursor/readme-posix-setup-a81c/tests/test_history.py` |  |

## 伏せたもの

- なし
