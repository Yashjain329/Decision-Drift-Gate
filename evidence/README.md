# Evidence provenance

`gemini-proposal.json` is a sanitized capture from a real Gemini call on synthetic Decision Drift Gate inputs. It is not a handwritten fixture.

- Provider model: `gemini-3.8-flash`.
- SDK: `google-genai` version `2.28.0`.
- The capture records its actual UTC time, source revision, input-content digest, accepted check and proposal fingerprint.
- Gemini selected `commit_then_503`, expecting one unique job and an existing returned job ID, with exact DEC-002 citations.
- API keys, request headers and raw SDK exceptions are excluded.

Use the application’s Recorded mode to replay this capture only when current input content matches. Recorded generation is disclosed; subsequent approved-check execution is fresh. Live mode makes a new provider request. A source revision from the original generated repository is provenance, not a claim that this SHA belongs to the source-code repository.

This capture demonstrates proposal generation. Calibration, approval, later execution, browser behavior and participant results require their own evidence in [phase status](../docs/phases/STATUS.md). No human review-time savings have been measured.
