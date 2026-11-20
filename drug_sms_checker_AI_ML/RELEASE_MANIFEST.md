# RELEASE MANIFEST — Drug SMS Checker AI/ML

Release name: `Drug_SMS_Checker_AI_ML`
Release date: 19 Nov 2026
Project version: no version identifier is declared anywhere in the source tree; this release is identified by its name and date only. No version was invented.
Directory: `release/Drug_SMS_Checker_AI_ML/`
Archive: `release/Drug_SMS_Checker_AI_ML.zip`

## Included directories and important files

- `(root)` - 5 file(s): `.env.example`, `.gitignore`, `HANDOFF_SUMMARY.md`, `README.md`, `requirements.txt`
- `data` - 28 file(s): `data/packaging/daylight/pack_01.jpeg`, `data/packaging/daylight/pack_02.jpeg`, `data/packaging/daylight/pack_03.jpeg`, `data/packaging/daylight/pack_04.jpeg`, `data/packaging/daylight/pack_05.jpeg`, `data/packaging/daylight/pack_06.jpeg` ...
- `docs` - 22 file(s): `docs/AI_ML_FUNCTIONALITY_AUDIT.md`, `docs/AI_ML_HANDOFF.md`, `docs/AI_ML_LIVE_TEST_REPORT.md`, `docs/AI_ML_PREREQUISITES.md`, `docs/BACKEND_INTEGRATION_GUIDE.md`, `docs/COMPETITION_DEMO_GUIDE.md` ...
- `src` - 14 file(s): `src/__init__.py`, `src/candidate.py`, `src/catalogue.py`, `src/contracts.py`, `src/decision.py`, `src/field_compare.py` ...
- `tests` - 16 file(s): `tests/conftest.py`, `tests/live/test_live_gemini.py`, `tests/photo_test_template.csv`, `tests/test_candidate.py`, `tests/test_catalogue.py`, `tests/test_decision.py` ...
- `tools` - 5 file(s): `tools/demo.py`, `tools/interactive_server.py`, `tools/interactive_ui.html`, `tools/photo_eval.py`, `tools/reconcile_packaging.py`

Key contents: all 14 `src/` modules, 16 test files including the opt-in live suite, 5 tools (demo, interactive server, interactive UI, packaging reconciliation, photo evaluation), the 40-record catalogue, 5 packaging CSVs, all 22 packaging images, documentation, `README.md`, `HANDOFF_SUMMARY.md`, `requirements.txt`, `.gitignore` and `.env.example`.

## Excluded sensitive and unnecessary files

- `.env` and every real API key or secret (the original `.env` remains untouched in the working project).
- `__pycache__`, `.pytest_cache`, `*.pyc`, `.playwright-mcp`, temporary logs and editor caches.
- Virtual environments, personal files, unrelated projects and generated artifacts outside the release.
- The release ZIP itself is stored beside, not inside, the release directory.

## Environment and dependencies

Verified on Windows 11, Python 3.14.6, PowerShell 5.1. Declared in `requirements.txt`: `pydantic>=2.7,<3`, `rapidfuzz>=3.9,<4`, `google-genai>=2.0,<3`, `python-dotenv>=1.0,<2`, `pytest>=8,<10`. No new dependency was introduced.

Configuration uses exactly three variables: `GEMINI_API_KEY`, `GEMINI_MODEL`, `AI_ML_MOCK`. `.env.example` contains placeholders only. The backend must supply the key through its secure secrets mechanism; no real key is present in this release.

## Test results

```text
python -m pytest -q
182 passed, 40 skipped, 0 failed, 2 warnings
```

Live Gemini validation: PARTIAL. Full live suite: not passed and not run for packaging. Real-world OCR accuracy: NOT TESTED (ground truth blank). Backend integration: PENDING APPROVAL, `AWAITING_BACKEND_CONFIRMATION = True`.

## Known limitations

40-record test catalogue; no packaging/catalogue registration-number overlap; blank ground truth; no measured OCR accuracy; Gemini latency with one earlier 180-second batch timeout; limited live coverage; package volume absent from the four-field `PhotoFields` schema; unapproved backend contract; production readiness not established. See `docs/KNOWN_LIMITATIONS_AND_NEXT_STEPS.md`.

## SHA-256 checksums

Checksums cover every packaged file except this manifest (which cannot hash itself) and the ZIP archive. Verify with `Get-FileHash -Algorithm SHA256` on Windows.

| File | SHA-256 |
| --- | --- |
| `.env.example` | `7034e1834ca3fff0c6e3182120e517e8faee1df70030465b5a8729cb8b4c65f9` |
| `.gitignore` | `3213914367823738f835061b45a57b3a6a625e7391c1eaa3a8e3205853b92eb2` |
| `data/packaging/daylight/pack_01.jpeg` | `cab2d4fded108e671892029be0f41891ab7c489373e3c89dcf492e540bffe412` |
| `data/packaging/daylight/pack_02.jpeg` | `ff39f37a02090a78eba226dbee80473ae6d9bec9e49d56f458b46a55f0d48c1b` |
| `data/packaging/daylight/pack_03.jpeg` | `8ae65b77e8ec8881bb4d0603d513412ef8cf1862c49cfc9e0efa222753c39b6d` |
| `data/packaging/daylight/pack_04.jpeg` | `e528d6d195d6722ab05ca672d2ed1c60c5d5c81b08b5c1ff53deef59a363ec5d` |
| `data/packaging/daylight/pack_05.jpeg` | `816c9ef106ec408f90812a6224e3f15f3e9f4dce96af5866d7cd83a125c3bd29` |
| `data/packaging/daylight/pack_06.jpeg` | `54b89c4cbbbcebdbbc72b1076fad340ecec1e6575348e08cf7adecf36155fb5d` |
| `data/packaging/daylight/pack_07.jpeg` | `e43c0b2af0c9b446edf2e7b6c2ea0f67e4516a4c67f31b1cb03e41098ae7b54e` |
| `data/packaging/daylight/pack_08.jpeg` | `7115c8e40d7e7f4e2b5a7e14c5dafa1eb36399d97f6c8f8d4a11e9fb1e3c2bb9` |
| `data/packaging/daylight/pack_09.jpeg` | `894a923d6a52e78aeeec51698a83ac38190e45228d83c522a108b587d16f9273` |
| `data/packaging/daylight/pack_10.jpeg` | `71066753cd598569b4e4887d1fae87e3644b921bcb15e41b524a326d71bbd367` |
| `data/packaging/daylight/pack_11.jpeg` | `a96ebaa9bd451899bbf907e7ae0616dfa61d30f099a0c99f6888cdf5bb1b7a3b` |
| `data/packaging/ground_truth.csv` | `9ac61fba1fca306e96591d6da34e1e47b4b5cb24a5272d6652238b4c9357f66c` |
| `data/packaging/indoor/pack_01..jpeg` | `a36abd63068398db2960a84c310a6288d0d11ba4b3297ccf104cd3dac6446ef4` |
| `data/packaging/indoor/pack_02.jpeg` | `9831584cd8572d98a389d0f23efaaa6e3abbda1ebc5d9afae981e2dd09cb5470` |
| `data/packaging/indoor/pack_03.jpeg` | `5a78910577a2a66a6ede3af2377a37c77553743294af667a9882c39b9dd1a37b` |
| `data/packaging/indoor/pack_04.jpeg` | `afd0cdf8aca2304e8d62a3ed95f571ec46ba56c989f3fdd26323bfaba24906a3` |
| `data/packaging/indoor/pack_05.jpeg` | `d2e32a036607bc62c5be967533d61136adecdc4d8bc69eaeacce3f1847046151` |
| `data/packaging/indoor/pack_06.jpeg` | `67fd0f45b0d883b4920d01ad75c2ef5452ac9535ca3045e27019f48547db7cce` |
| `data/packaging/indoor/pack_07.jpeg` | `3a7a3d25fa56f8e23e91ec68e5b4e104c71ce47a3ace49bb017334a278f8ab19` |
| `data/packaging/indoor/pack_08.jpeg` | `6c9d4b25445721ba2e64cec4f74c048d9525f1186e41ad158de8298c1debfb85` |
| `data/packaging/indoor/pack_09.jpeg` | `56f89efa5380ab8159c29a08ea41015b49c15e80711ebf4e7a52a86a0fa36fd3` |
| `data/packaging/indoor/pack_10.jpeg` | `361d9ecf7145dd3cb3cbba28aab0c6cc29aa7e3c7935f79d7626ba0238ae7e90` |
| `data/packaging/indoor/pack_11.jpeg` | `288e115f591610b0d6322c7e9e9471ca60d5dba330c663a0aff6e4f9327eb5d6` |
| `data/packaging/ocr_results.csv` | `2c5f03d958794c67adf5af36cc1b7545a80eaa90d6eaf97fd85a49fcbba2de7b` |
| `data/packaging/ocr_results.original.csv` | `016125dc5aa253139e7e0a62b7b1acdd77570d73618bc59d581e1aa971c0767b` |
| `data/packaging/package_results.csv` | `faec5b22f6eff5dac3bd5c4582cfbf1137f1a8f7a73546e69e903108466a2967` |
| `data/packaging/package_results.pre_reconciliation.csv` | `481aebc08c2cbbebe9d1a68858a0178b6204bd95f7bc29503724d85edbf38b19` |
| `data/test_drugs.csv` | `abc9535416dd49eec221612aeea89d9c30ee42bd93804eaa664350287b514635` |
| `docs/AI_ML_FUNCTIONALITY_AUDIT.md` | `ce49d80e7940530cd47f2f68e9471d12891495aca345a968ebb5d6182ac389d5` |
| `docs/AI_ML_HANDOFF.md` | `ae4486e3b264819c27153cc65a2f636f4eefff60c77969711f3f0de5c8e6caf2` |
| `docs/AI_ML_LIVE_TEST_REPORT.md` | `95006895b6a9fdd9f89a02d2c571fccbc1080f413735b29f516e85d7aca0e0bb` |
| `docs/AI_ML_PREREQUISITES.md` | `023243b5a182916ace68e50811ae4b3a2ef97def6613b5b925927b654dd4ddf4` |
| `docs/BACKEND_INTEGRATION_GUIDE.md` | `30c97ebece1e6add5bcb03196ffc6ab151fcbd822b00a18a840cd99f1c83c843` |
| `docs/COMPETITION_DEMO_GUIDE.md` | `82591c20699177ba67dda8eb017704cdeec656bda950dc886db94c56805b8596` |
| `docs/Drug SMS Checker Problem Statement and Solution.pdf` | `86c35c56707ff71621e2fc6a42880f56a2451ab6d04b9f65255e52ac1433c600` |
| `docs/Drug SMS Checker Team Guide by Role.pdf` | `0e8ddff9d06deafd1ea658253be803582f4bb3e13f994e5b036b77ef5a72d8cd` |
| `docs/FEATURE_COMPLETION_MATRIX.md` | `e921be1f4037644f367fe1a8d8dd7913c91f0e5a29d6cd538d15e8139c6dec3d` |
| `docs/FINAL_AI_ML_HANDOFF.md` | `bb9407d9f4e0eeb7ed699537436b6e7545847cf5a20dc61dc1f3301b7be67719` |
| `docs/FINAL_IMPLEMENTATION_AUDIT.md` | `3053cf67b948e661efc84b1e0882f5de26c127693ba7041bfd1ae5bf2f01d7dd` |
| `docs/GROUND_TRUTH_STATUS.md` | `c08bda4ce9b64bf262daf7245862665ee20bf741d9a6cc7482c1c0fbf473880d` |
| `docs/INTERACTIVE_TESTING_GUIDE.md` | `7975a2e871fdf6b226202c10808d66211a399edfdf09a998c186e3cd3ae1ae41` |
| `docs/KNOWN_LIMITATIONS_AND_NEXT_STEPS.md` | `f4f9f597f519b5d593b5e571efafac87ddc30d2a47ae925f3b6c27b50e9ba8f1` |
| `docs/MEDICINE_DATABASE_READINESS_AUDIT.md` | `0f1d58755271453d46965ed3ded9d6f20e6d0681cf8514e60a9dae035c9beeba` |
| `docs/OCR_PERFORMANCE_AUDIT.md` | `6e20396808343f6a0cfaf270cb6939992ec8462a6549c33c163f47ebdb513615` |
| `docs/PACKAGING_DATASET_VALIDATION.md` | `adb7af81fcad27905943fe46e8cb22ede03b6397676f89f53c31479ad9914766` |
| `docs/PHOTO_COMPARISON_REPORT.md` | `d3b76305661f1489e6dca487a832e6f3b33d06289f62c83e820b53a4e2423fec` |
| `docs/PROJECT_CURRENT_STATE_AUDIT.md` | `0408dbdd1fb65b83fa927c65b8e9b922a485bc5b7670a004666db2d09b85b3f8` |
| `docs/TESTING_AND_VALIDATION_REPORT.md` | `1e4999d76c31ca4c59150a5cd5e27640ae21ea76a026657959648b9a890ecd83` |
| `docs/VERIFICATION_ENGINE.md` | `ac27e042e970da7a343fb2834836fa5380d4fd271f9d3d6fc6ffb42c772bdeb7` |
| `docs/VERIFICATION_PERFORMANCE_AUDIT.md` | `6395e3b665aa6693cd77f0483d6a15594bbe1725d8002d15d4730011240580bd` |
| `HANDOFF_SUMMARY.md` | `9e1c28ff9232f950602c237115434d9237133d3e32d977635c8b33b4b562f95d` |
| `README.md` | `85118ac3895b2725a802950afc84c24542ff14a21e66d6ad3a07cdd23667dc0e` |
| `requirements.txt` | `0b95f5ce9c31b61d41a60adea61ed0111079fdc006375b82fced203caa3c3ad9` |
| `src/__init__.py` | `5991d030b0878987fc6f9437c3fc18fb09c3409bd0a8526769fc2a3712c5e779` |
| `src/candidate.py` | `8789948a5d35c3cce7af29ca5f1b0757be91cad68a098759b0a8eee7036f6122` |
| `src/catalogue.py` | `82c8d49ba6552620168351160093fd1ac5d274a0c3dbdc42744eb2422b88f832` |
| `src/contracts.py` | `bcdf9533276074e9ac40d26311662562e8a5439f0b421734756e0548597a8157` |
| `src/decision.py` | `a275ab1283a073fbddf6a1c167133e97ee28d2b425e2daded1eaa0b43acf7990` |
| `src/field_compare.py` | `6f5a87ca5d173dcd03af37a5cdadf4e8ce72a940988201764ff10a2e47c1e999` |
| `src/fuzzy.py` | `4334c1d977fdb9740283ffa30aef40fd49dce7593fd8a6c42b7950debdbe26de` |
| `src/gemini.py` | `bcc8994a6f4594d1909bb6e1cfa42410cf547d91b043186aedf95d6cd32ba95a` |
| `src/message.py` | `f9be68ba72987fd2863c3d9c7f5077739240330bf66c610b159df2036abdd1fe` |
| `src/observation.py` | `a64d09134c143e801fbfdb517bbe2e9431b041d181093788c17bcae824f74fe2` |
| `src/packaging.py` | `9e2d94b7d7cee1a1ecfc80e392cf60434246659a92c469cddd0bac392b4b0210` |
| `src/photo.py` | `bd1f16cf245c67cba9a7f37d9328eb99011b2256a6e3605d518f0767a9c50875` |
| `src/pipeline.py` | `8fe19d9199f970bceb2c5ec829b7db3d1f1c8bd8eeb7933218083214dd795526` |
| `src/verification.py` | `49fb0f11054e942be05f08f1c45f37ec0aa689d21a749bf0143b2ebe897141af` |
| `tests/conftest.py` | `4a2ab963b7fc44147ebfd3e2ec866cdbe27a27031a21a954c4c059486d76b043` |
| `tests/live/test_live_gemini.py` | `9c9fb1abdedbb0650f9643cd7fdbc9dcea1cc1570906d2450a45c0ec1235545b` |
| `tests/photo_test_template.csv` | `c854ecfff969c2e26fc9190aa31d8713da8c0278838147948924b392c7db107d` |
| `tests/test_candidate.py` | `bd9eb1e34c8f62cd77fc4ecf9df84e9154aa743e2500fc83c8626b5cdcf6d7fa` |
| `tests/test_catalogue.py` | `7d4dc5fe46d92e3efedc16f2346e3d5000fbdba1d51914a24e718b608e8a14f9` |
| `tests/test_decision.py` | `4a661166363f23e13a263071a4218d344e6d23c35fa119b6fdd6c7b449751ecc` |
| `tests/test_field_compare.py` | `ad870a2f688848b901e2569fe3aea7f053464deb62c0afaf48dfe62c1b45a9b9` |
| `tests/test_fuzzy.py` | `2db2c808a21d53b1d6136ccb55a3463fa440ae65f8049b41d58b71c94beeae2d` |
| `tests/test_gemini.py` | `1061bc5b0350537f396a4a42197acd58c7148cce547daa5e0950688fafab921d` |
| `tests/test_ground_truth.py` | `cc660d5b6cd5813f39f405cf9767a31f112b1eeda0784959db5db2fc50258265` |
| `tests/test_integration.py` | `10a1e8b74d302b0211edd916f8be526b3021e26eb60f4c686f401bcd3d165a08` |
| `tests/test_message.py` | `8c1693229e72c543ffc80c2a509c5d00497434c58909da57774576ed6694a9b8` |
| `tests/test_packaging.py` | `4613b624fe245072f6639366dd5ccc16eaf58bb5a7d8af25c7668bdc5504dbd2` |
| `tests/test_photo.py` | `c506c91c8e94efd38562e2911445772ec67e2a32ef2a959b213da22dd8c329ca` |
| `tests/test_photo_api_errors.py` | `d0bf1cd13e6de07aa57d1dadcac0c335c70395027be9eb5d72b926caad8e9825` |
| `tests/test_verification.py` | `6532cf66886063554df2f17752cbcb0b9c9d99c2c802ac31404a0e5fb32434db` |
| `tools/demo.py` | `99131f76f7da67f8aab8915952a0692d78b598be4b2d07680bce142c1d91e50c` |
| `tools/interactive_server.py` | `a5cfa93ee678b1bcc33020960caf30fbb85875bac6d45aa3c764ae066ad66cbc` |
| `tools/interactive_ui.html` | `bf3d65b84b5c4ec32763def862b4ec499fd71b15765280978ea05b824f1c7a22` |
| `tools/photo_eval.py` | `84ec9030d60735c5a89e63a7c16f0b20b9f1992fa261aad7d8cefb43f3a7bfb7` |
| `tools/reconcile_packaging.py` | `f064ad2b067579477b257201cc96ed0814f31d3a3819938f0dea3d5da42a4d19` |
