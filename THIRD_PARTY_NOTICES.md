# THIRD-PARTY NOTICES

Сгенерировано из SBOM (`json/sbom.cdx.json`) `2026-11-08`.

XTTS Studio AI включает сторонние библиотеки и модели. Каждая лицензируется
на условиях её правообладателя и **независимо** от лицензии самого проекта
(см. [LICENSE.md](./LICENSE.md)). Использование стороннего компонента не означает
разрешения на коммерческое использование сверх того, что допускает его лицензия.

## Ключевые компоненты и их лицензии

| Компонент | Лицензия | Коммерческое использование |
|-----------|----------|----------------------------|
| XTTS Studio (код проекта) | [LICENSE.md](./LICENSE.md) | разрешено при условиях лицензии |
| XTTS v2 (модель) | [Coqui Public Model License (CPML)](https://coqui.ai/cpml) | ограничено CPML |
| PyTorch | BSD-3-Clause | OK |
| RVC-модели (community) | зависит от автора модели | не подразумевается |
| GGUF-модели (catalog) | зависит от автора модели | не подразумевается |

CPML ограничивает коммерческое использование XTTS v2. RVC/GGUF-модели, доступные
через каталог, имеют собственные лицензии авторов; возможность скачать файл или
его наличие в каталоге **не является** разрешением на коммерческое использование.

## Зависимости рантайма (из SBOM)

Полный список зафиксированных рантайм-зависимостей (source: `requirements.txt`,
через SBOM). Подробные лицензии per-пакета — на страницах пакетов по ссылке.

- **Cython** `3.2.5` — pkg:pypi/cython@3.2.5
- **DAWG-Python** `0.7.2` — pkg:pypi/dawg-python@0.7.2
- **DAWG2-Python** `0.9.0` — pkg:pypi/dawg2-python@0.9.0
- **Flask** `3.1.3` — pkg:pypi/flask@3.1.3
- **Jinja2** `3.1.6` — pkg:pypi/jinja2@3.1.6
- **Markdown** `3.10.2` — pkg:pypi/markdown@3.10.2
- **MarkupSafe** `3.0.3` — pkg:pypi/markupsafe@3.0.3
- **PyYAML** `6.0.3` — pkg:pypi/pyyaml@6.0.3
- **Pygments** `2.20.0` — pkg:pypi/pygments@2.20.0
- **SudachiDict-core** `20260428` — pkg:pypi/sudachidict-core@20260428
- **SudachiPy** `0.6.11` — pkg:pypi/sudachipy@0.6.11
- **TTS** `0.22.0` — pkg:pypi/tts@0.22.0
- **Unidecode** `1.4.0` — pkg:pypi/unidecode@1.4.0
- **Werkzeug** `3.1.9` — pkg:pypi/werkzeug@3.1.9
- **absl-py** `2.4.0` — pkg:pypi/absl-py@2.4.0
- **aiohappyeyeballs** `2.6.2` — pkg:pypi/aiohappyeyeballs@2.6.2
- **aiohttp** `3.14.4` — pkg:pypi/aiohttp@3.14.4
- **aiosignal** `1.4.0` — pkg:pypi/aiosignal@1.4.0
- **annotated-doc** `0.0.4` — pkg:pypi/annotated-doc@0.0.4
- **annotated-types** `0.7.0` — pkg:pypi/annotated-types@0.7.0
- **antlr4-python3-runtime** `4.9.3` — pkg:pypi/antlr4-python3-runtime@4.9.3
- **anyascii** `0.3.3` — pkg:pypi/anyascii@0.3.3
- **anyio** `4.14.2` — pkg:pypi/anyio@4.14.2
- **attrs** `26.1.0` — pkg:pypi/attrs@26.1.0
- **audioread** `3.1.0` — pkg:pypi/audioread@3.1.0
- **av** `12.3.0` — pkg:pypi/av@12.3.0
- **babel** `2.18.0` — pkg:pypi/babel@2.18.0
- **bangla** `0.0.6` — pkg:pypi/bangla@0.0.6
- **bitarray** `3.9.0` — pkg:pypi/bitarray@3.9.0
- **blinker** `1.9.0` — pkg:pypi/blinker@1.9.0
- **blis** `1.3.3` — pkg:pypi/blis@1.3.3
- **bnnumerizer** `0.0.2` — pkg:pypi/bnnumerizer@0.0.2
- **bnunicodenormalizer** `0.1.7` — pkg:pypi/bnunicodenormalizer@0.1.7
- **catalogue** `2.0.10` — pkg:pypi/catalogue@2.0.10
- **certifi** `2026.10.18` — pkg:pypi/certifi@2026.10.18
- **cffi** `2.0.0` — pkg:pypi/cffi@2.0.0
- **charset-normalizer** `3.4.7` — pkg:pypi/charset-normalizer@3.4.7
- **click** `8.4.1` — pkg:pypi/click@8.4.1
- **cloudpathlib** `0.24.0` — pkg:pypi/cloudpathlib@0.24.0
- **colorama** `0.4.6` — pkg:pypi/colorama@0.4.6
- **confection** `1.3.3` — pkg:pypi/confection@1.3.3
- **contourpy** `1.3.3` — pkg:pypi/contourpy@1.3.3
- **coqpit** `0.0.17` — pkg:pypi/coqpit@0.0.17
- **cryptography** `50.0.0` — pkg:pypi/cryptography@50.0.0
- **customtkinter** `6.0.0` — pkg:pypi/customtkinter@6.0.0
- **cycler** `0.12.1` — pkg:pypi/cycler@0.12.1
- **cymem** `2.0.13` — pkg:pypi/cymem@2.0.13
- **darkdetect** `0.8.0` — pkg:pypi/darkdetect@0.8.0
- **dateparser** `1.1.8` — pkg:pypi/dateparser@1.1.8
- **decorator** `5.3.1` — pkg:pypi/decorator@5.3.1
- **docopt** `0.6.2` — pkg:pypi/docopt@0.6.2
- **einops** `0.8.2` — pkg:pypi/einops@0.8.2
- **encodec** `0.1.1` — pkg:pypi/encodec@0.1.1
- **faiss-cpu** `1.14.3` — pkg:pypi/faiss-cpu@1.14.3
- **fastapi** `0.139.0` — pkg:pypi/fastapi@0.139.0
- **ffmpeg-python** `0.2.0` — pkg:pypi/ffmpeg-python@0.2.0
- **filelock** `4.2.1` — pkg:pypi/filelock@4.2.1
- **fonttools** `4.63.0` — pkg:pypi/fonttools@4.63.0
- **frozenlist** `1.8.0` — pkg:pypi/frozenlist@1.8.0
- **fsspec** `2026.6.0` — pkg:pypi/fsspec@2026.6.0
- **future** `1.0.0` — pkg:pypi/future@1.0.0
- **g2pkk** `0.1.2` — pkg:pypi/g2pkk@0.1.2
- **grpcio** `1.81.0` — pkg:pypi/grpcio@1.81.0
- **gruut** `2.2.3` — pkg:pypi/gruut@2.2.3
- **gruut-ipa** `0.13.0` — pkg:pypi/gruut-ipa@0.13.0
- **gruut_lang_de** `2.0.1` — pkg:pypi/gruut-lang-de@2.0.1
- **gruut_lang_en** `2.0.1` — pkg:pypi/gruut-lang-en@2.0.1
- **gruut_lang_es** `2.0.1` — pkg:pypi/gruut-lang-es@2.0.1
- **gruut_lang_fr** `2.0.2` — pkg:pypi/gruut-lang-fr@2.0.2
- **h11** `0.16.0` — pkg:pypi/h11@0.16.0
- **hangul-romanize** `0.1.0` — pkg:pypi/hangul-romanize@0.1.0
- **hf-xet** `1.5.1` — pkg:pypi/hf-xet@1.5.1
- **httpcore** `1.0.9` — pkg:pypi/httpcore@1.0.9
- **httpx** `0.28.1` — pkg:pypi/httpx@0.28.1
- **huggingface_hub** `0.36.2` — pkg:pypi/huggingface-hub@0.36.2
- **hydra-core** `1.3.8` — pkg:pypi/hydra-core@1.3.8
- **idna** `3.18` — pkg:pypi/idna@3.18
- **inflect** `7.5.0` — pkg:pypi/inflect@7.5.0
- **itsdangerous** `2.2.0` — pkg:pypi/itsdangerous@2.2.0
- **jamo** `0.4.1` — pkg:pypi/jamo@0.4.1
- **jieba** `0.42.1` — pkg:pypi/jieba@0.42.1
- **joblib** `1.5.3` — pkg:pypi/joblib@1.5.3
- **jsonlines** `1.2.0` — pkg:pypi/jsonlines@1.2.0
- **kiwisolver** `1.5.0` — pkg:pypi/kiwisolver@1.5.0
- **lazy-loader** `0.5` — pkg:pypi/lazy-loader@0.5
- **librosa** `0.11.0` — pkg:pypi/librosa@0.11.0
- **llvmlite** `0.47.0` — pkg:pypi/llvmlite@0.47.0
- **loguru** `0.7.3` — pkg:pypi/loguru@0.7.3
- **lxml** `6.1.1` — pkg:pypi/lxml@6.1.1
- **markdown-it-py** `4.2.0` — pkg:pypi/markdown-it-py@4.2.0
- **matplotlib** `3.10.9` — pkg:pypi/matplotlib@3.10.9
- **mdurl** `0.1.2` — pkg:pypi/mdurl@0.1.2
- **more-itertools** `11.1.0` — pkg:pypi/more-itertools@11.1.0
- **mpmath** `1.3.0` — pkg:pypi/mpmath@1.3.0
- **msgpack** `1.2.3` — pkg:pypi/msgpack@1.2.3
- **multidict** `6.9.1` — pkg:pypi/multidict@6.9.1
- **murmurhash** `1.0.15` — pkg:pypi/murmurhash@1.0.15
- **narwhals** `2.22.1` — pkg:pypi/narwhals@2.22.1
- **networkx** `2.8.8` — pkg:pypi/networkx@2.8.8
- **nltk** `3.10.4` — pkg:pypi/nltk@3.10.4
- **num2words** `0.5.14` — pkg:pypi/num2words@0.5.14
- **numba** `0.65.1` — pkg:pypi/numba@0.65.1
- **numpy** `1.26.4` — pkg:pypi/numpy@1.26.4
- **omegaconf** `2.3.1` — pkg:pypi/omegaconf@2.3.1
- **packaging** `26.2` — pkg:pypi/packaging@26.2
- **pandas** `1.5.3` — pkg:pypi/pandas@1.5.3
- **pillow** `13.0.0` — pkg:pypi/pillow@13.0.0
- **platformdirs** `4.10.0` — pkg:pypi/platformdirs@4.10.0
- **playsound** `1.2.2` — pkg:pypi/playsound@1.2.2
- **pooch** `1.9.0` — pkg:pypi/pooch@1.9.0
- **portalocker** `3.2.0` — pkg:pypi/portalocker@3.2.0
- **praat-parselmouth** `0.4.7` — pkg:pypi/praat-parselmouth@0.4.7
- **preshed** `3.0.13` — pkg:pypi/preshed@3.0.13
- **propcache** `0.5.2` — pkg:pypi/propcache@0.5.2
- **protobuf** `7.35.0` — pkg:pypi/protobuf@7.35.0
- **psutil** `7.2.2` — pkg:pypi/psutil@7.2.2
- **py-cpuinfo** `9.0.0` — pkg:pypi/py-cpuinfo@9.0.0
- **pycparser** `3.0` — pkg:pypi/pycparser@3.0
- **pydantic** `2.13.4` — pkg:pypi/pydantic@2.13.4
- **pydantic_core** `2.46.4` — pkg:pypi/pydantic-core@2.46.4
- **pydub** `0.25.1` — pkg:pypi/pydub@0.25.1
- **pygame** `2.6.1` — pkg:pypi/pygame@2.6.1
- **pymorphy2-dicts** `2.4.393442.3710985` — pkg:pypi/pymorphy2-dicts@2.4.393442.3710985
- **pynndescent** `0.6.0` — pkg:pypi/pynndescent@0.6.0
- **pyparsing** `3.3.2` — pkg:pypi/pyparsing@3.3.2
- **pypinyin** `0.55.0` — pkg:pypi/pypinyin@0.55.0
- **pysbd** `0.3.4` — pkg:pypi/pysbd@0.3.4
- **python-crfsuite** `0.9.12` — pkg:pypi/python-crfsuite@0.9.12
- **python-dateutil** `2.9.0.post0` — pkg:pypi/python-dateutil@2.9.0.post0
- **python-multipart** `0.0.32` — pkg:pypi/python-multipart@0.0.32
- **pytz** `2026.2` — pkg:pypi/pytz@2026.2
- **pywin32** `312` — pkg:pypi/pywin32@312
- **pyworld** `0.3.5` — pkg:pypi/pyworld@0.3.5
- **regex** `2026.5.9` — pkg:pypi/regex@2026.5.9
- **requests** `2.34.2` — pkg:pypi/requests@2.34.2
- **resampy** `0.4.3` — pkg:pypi/resampy@0.4.3
- **rich** `15.0.0` — pkg:pypi/rich@15.0.0
- **sacrebleu** `2.6.0` — pkg:pypi/sacrebleu@2.6.0
- **safetensors** `0.7.0` — pkg:pypi/safetensors@0.7.0
- **scikit-learn** `1.9.0` — pkg:pypi/scikit-learn@1.9.0
- **scipy** `1.17.1` — pkg:pypi/scipy@1.17.1
- **shellingham** `1.5.4` — pkg:pypi/shellingham@1.5.4
- **six** `1.17.0` — pkg:pypi/six@1.17.0
- **smart_open** `7.6.1` — pkg:pypi/smart-open@7.6.1
- **soundfile** `0.14.0` — pkg:pypi/soundfile@0.14.0
- **soxr** `1.1.0` — pkg:pypi/soxr@1.1.0
- **spacy** `3.8.14` — pkg:pypi/spacy@3.8.14
- **spacy-legacy** `3.0.12` — pkg:pypi/spacy-legacy@3.0.12
- **spacy-loggers** `1.0.5` — pkg:pypi/spacy-loggers@1.0.5
- **srsly** `2.5.3` — pkg:pypi/srsly@2.5.3
- **starlette** `1.3.1` — pkg:pypi/starlette@1.3.1
- **sympy** `1.14.0` — pkg:pypi/sympy@1.14.0
- **tabulate** `0.10.0` — pkg:pypi/tabulate@0.10.0
- **tensorboard** `2.20.0` — pkg:pypi/tensorboard@2.20.0
- **tensorboard-data-server** `0.7.2` — pkg:pypi/tensorboard-data-server@0.7.2
- **thinc** `8.3.13` — pkg:pypi/thinc@8.3.13
- **threadpoolctl** `3.6.0` — pkg:pypi/threadpoolctl@3.6.0
- **tkinterdnd2** `0.4.4.1` — pkg:pypi/tkinterdnd2@0.4.4.1
- **tokenizers** `0.15.2` — pkg:pypi/tokenizers@0.15.2
- **torch** `2.2.2` — pkg:pypi/torch@2.2.2
- **torchaudio** `2.2.2` — pkg:pypi/torchaudio@2.2.2
- **torchcrepe** `0.0.24` — pkg:pypi/torchcrepe@0.0.24
- **torchvision** `0.17.2` — pkg:pypi/torchvision@0.17.2
- **tqdm** `4.68.1` — pkg:pypi/tqdm@4.68.1
- **trainer** `0.0.36` — pkg:pypi/trainer@0.0.36
- **transformers** `4.38.2` — pkg:pypi/transformers@4.38.2
- **typeguard** `4.5.2` — pkg:pypi/typeguard@4.5.2
- **typer** `0.25.1` — pkg:pypi/typer@0.25.1
- **typing-inspection** `0.4.2` — pkg:pypi/typing-inspection@0.4.2
- **typing_extensions** `4.15.0` — pkg:pypi/typing-extensions@4.15.0
- **tzdata** `2026.2` — pkg:pypi/tzdata@2026.2
- **tzlocal** `5.3.1` — pkg:pypi/tzlocal@5.3.1
- **umap-learn** `0.5.12` — pkg:pypi/umap-learn@0.5.12
- **urllib3** `2.8.0` — pkg:pypi/urllib3@2.8.0
- **uvicorn** `0.51.0` — pkg:pypi/uvicorn@0.51.0
- **wasabi** `1.1.3` — pkg:pypi/wasabi@1.1.3
- **weasel** `1.0.0` — pkg:pypi/weasel@1.0.0
- **win32_setctime** `1.2.0` — pkg:pypi/win32-setctime@1.2.0
- **wrapt** `2.2.1` — pkg:pypi/wrapt@2.2.1
- **yarl** `1.24.2` — pkg:pypi/yarl@1.24.2

---

*Файл генерируется; не редактируйте вручную — перегенерируйте через `tools/generate_third_party_notices.py`.*
