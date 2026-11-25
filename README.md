# Taodock Catalog Copy Audit for AI Verify Toolkit

Review AI-written product listings against approved specifications before they go live. This independent AI Verify Toolkit plugin checks English drafts for missing measurements, extra measurements and missing required phrases. Its report widget shows which SKUs need review and what to check. It is designed for catalog and QA teams, including Singapore sellers using English product copy.

The audit runs locally with Python 3.10 or later and has no third-party Python requirements. The plugin targets AI Verify Toolkit 2.2.2. Drafts can come from an existing catalog or be generated with Taodock using the optional command below.

## Install the plugin and see a report

1. Download `taodock.catalog-copy-audit-0.1.0.zip` from [GitHub Releases](https://github.com/taodock-api/taodock-aiverify/releases). In Toolkit, open **Manage → Plugins → Upload Plugin** and upload the ZIP.
2. Extract a copy of the install ZIP to a working directory. From that directory, score the 15 fictional Singapore catalog entries.

   ```sh
   python3 audit_catalog.py score examples/catalog.csv sample-results.zip
   ```

   The expected result is 15 checked, 8 passed and 7 flagged.
3. In Toolkit, go to **Manage → Results → Upload Test Results**, select the ZIP option and upload `sample-results.zip`.
4. In a project report, add **Catalog Copy Findings** to the canvas. On the data selection step, select the result for **Catalog Copy Audit**. The imported result uses a Toolkit model label named **Taodock catalog copy - pre-generated drafts.txt**. This label satisfies the result import format and does not require a model upload. The audit scores the supplied text.

[AI Verify installation and plugin upload guide](https://aiverify-foundation.github.io/aiverify-developer-tools/guided_example/deploy_your_plugin/)

## Use your own CSV

Use UTF-8 CSV with exactly these four headers. The file can contain 1–500 distinct SKUs. Each draft can contain up to 4,000 characters. Supply at least one measurement or required phrase per SKU and use a pipe (`|`) between entries in the same field.

| Header | Example |
| --- | --- |
| `sku` | `SG-001` |
| `measurements` | `30 cm\|500 ml` |
| `required_phrases` | `stainless steel\|navy blue` |
| `draft` | `Navy blue stainless steel holder, 30 cm long, with a 500 mL bottle.` |

The scorer recognises `mm`, `cm`, `m`, `g`, `kg`, `ml`, `L`, `W`, `kW`, `hours`, `minutes`, `pieces`, `%` and the abbreviations used in the sample. Equivalent measurements such as `1 L` and `1000 ml` match. Text matching ignores letter case and normalises whitespace. An unlisted measurement can indicate an error or an incomplete reference.

Use explicit numbers and units for each measurement. The audit compares quantities as a set and does not establish which attribute a quantity belongs to. It does not understand number words, ranges, implied units, negation, or paraphrased attributes. A passing audit means the configured checks found no discrepancy. Human review remains necessary for business and regulatory claims.

The audit does not make network requests. Its results contain SKU identifiers and values related to findings, so protect the result ZIP and report as you would the source catalog.

## Generate drafts with Taodock

Include the product type among the required phrases when it matters to the draft. Set `TAODOCK_API_KEY` securely in your shell and use an exact Chat Completions model ID available to your key. See the [Taodock API documentation](https://docs.taodock.com/en/api/overview.html). The command checks model access at `https://taodock.com/v1/models`, then submits each row's specified measurements and required phrases to `/v1/chat/completions`. This uses your API quota and overwrites the draft column in the new output CSV. The source CSV stays intact.

```sh
python3 audit_catalog.py generate examples/catalog.csv drafts.csv --model YOUR_MODEL_ID
python3 audit_catalog.py score drafts.csv results.zip
```

## Build from source

```sh
python3 -m unittest discover -s tests -v
python3 scripts/package.py
cd dist
shasum -a 256 -c SHA256SUMS
```

The AI Verify algorithm adapter uses the Apache-2.0-licensed AI Verify Test Engine interface. The stand-alone scorer and sample run do not require it. This project is published under the [MIT licence](LICENSE).
