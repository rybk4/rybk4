# WakaTime language logos

The local `language-icons.json` catalog contains 139 Devicon SVG logos and 279
normalized names and aliases. It covers programming languages, shells, markup,
stylesheets, common data formats and component formats such as JSX, TSX and Vue.
The source revision and each original asset path are recorded in the JSON.

Source: [Devicon](https://github.com/devicons/devicon), MIT license; see
`LICENSE-devicon.txt`. Logos belong to their respective projects and owners.

The generator embeds vector geometry directly in the output SVG. Rendering uses
no CDN, network requests, extra Python packages, web fonts or linked images.
One-color logos inherit theme-aware ink; selected multicolor logos have lighter
dark-theme paint so their dark lettering stays visible. Gradient IDs are unique
per placement.
Language matching ignores case, whitespace, dots, hyphens and underscores, while
keeping `C`, `C++` and `C#` distinct. WakaTime still determines the top five entries.

Languages without a catalog logo receive a monogram from their own name. This
also covers newly introduced languages without inventing a project logo. `Other`
and `More languages` keep their aggregate symbols.

To refresh the pinned catalog manually:

```sh
python .github/scripts/update_language_icons.py
python -m unittest discover -s .github/scripts -p 'test_*.py'
```

The updater caches original downloads in the ignored `output/devicon-cache/`
directory, flattens source CSS, strips editor metadata and rejects external image
resources. It is not part of the daily Actions workflow. To add another logo,
update `EXTRA_ICONS` / `ALIASES` in the updater and regenerate the catalog.
