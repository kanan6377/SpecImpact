# SpecImpact frontend

The production GUI is a React and TypeScript application compiled by Vite into
`specimpact/webui/static/dist/`. End users receive those assets in the Python package and do not
need Node.js.

```powershell
npm install
npm run check
npm run build
```

The frontend must use the FastAPI project APIs. Do not add runtime CDN dependencies, remote fonts,
or mock-data fallbacks to the production bundle.
