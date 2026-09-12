# site

The landing page, also served at https://yanqing.app/supreme-metric.

| file | what |
|---|---|
| `index.html` | the page: hero, the question film, the three-step answer film, the three rules, footer |
| `walk-out.html` | the question film on wide screens: the artifact's Walk-Out, verbatim, on a scaled 1180×700 stage |
| `six-questions-apple.html` | the question film on phones and tablets, embedded by `index.html`. Four teams walk out and shout eight true claims; "Govern the metrics" snaps them into one governed topology |
| `metric-film.html` | the answer film, embedded by `index.html`. Three steps: define the standard, review every metric against it, ship what passes |
| `govern.html` | an earlier playable page: drag metrics into a question and watch a JS port of the linter accept or reject them. Kept for reference; not linked from the landing page |

No build step. The only external resource is system fonts. Serve the folder over HTTP to view it; `file://` blocks the iframes.

```bash
python3 -m http.server 8765 --directory site
open http://localhost:8765/
```

The films embed the reference registry's questions and metrics as static content. `dist/topology.json` is the authoritative form; rendering the page from it is on the roadmap.
