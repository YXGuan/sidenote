# sidenote logo

`sidenote.svg` is the original margin-and-notes mark. The library uses the same
geometry in `SidenoteLogo.tsx`, inheriting its light or dark theme colors.
The extension uses the blue mark for its app icon, gray for inactive toolbar
buttons, and blue for active buttons.

After editing the vector, run `node tools/render_brand.mjs` with the local client
dependencies and Playwright Chromium installed. Then export the native patches
and rebuild, as described in [development](../docs/DEVELOPMENT.md).
