# Software bill of materials

- `viewer.cdx.json`: CycloneDX 1.5 list of the npm packages in the production dependency tree of the browser viewer (`web/`). The built viewer in `web/out` is bundled from these packages. Regenerate it with `npm run sbom` in `web/` after a dependency change. Development tools (TypeScript, Playwright, axe) are not listed because they are not shipped.
- The Python package `decision-drift-gate` has no runtime dependencies. It uses only the Python standard library. The optional extras are `ai` (`google-genai==2.28.0`) and `bedrock` (`boto3>=1.35`). They are listed in `pyproject.toml` and are not installed by default.
- The default sandbox image is `python:3.12-slim`, pulled at run time and not part of the package. Pin it by digest with `DDG_SANDBOX_IMAGE` or the Action input `sandbox-image`. Each report records the image and whether it was pinned.
