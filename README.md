# translator

A small interactive text translator built with [Panel](https://panel.holoviz.org/) and
[deep-translator](https://github.com/nidhaloff/deep-translator).

## Setup

```
pip install -r requirements.txt
```

## Run

Web UI:

```
panel serve translator.py --show
```

Terminal demo (prints three sample translations):

```
python translator.py
```

## Notes

- Uses the unofficial free Google Translate endpoint, which may be rate-limited or change.
  For production use, switch to the official Cloud Translation API or DeepL.
- Long input is split into chunks under ~5,000 characters automatically.
