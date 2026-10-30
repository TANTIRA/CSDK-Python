# Converge SDK for Python

`converge-sdk` calls the Converge platform's REST API from Python. It uses the standard library only and needs Python 3.9 or newer.

It has three parts:

- **`converge_sdk.core`** holds configuration, authentication, the HTTP transport and errors.
- **`converge_sdk.datasets`** covers datasets (catalog, branches, schema, transactions, files, rows) and SQL.
- **`converge_sdk.ontologies`** covers objects, links, actions, queries, aggregations and attachments. They are untyped, by API name. A generated ontology package builds its typed classes on this module.

## Install

```sh
pip install converge-sdk
```

Your platform may also serve the package from its own package index, next to your generated ontology package. See "Generated ontology packages" below.

## Authentication and configuration

The client needs your platform's API base URL (for example `https://converge.example.com/api`) and a token. It looks for them in this order:

1. The arguments: `ConvergeClient("https://converge.example.com/api", token=...)`.
2. The environment: `CONVERGE_HOSTNAME` and `CONVERGE_TOKEN`. `FOUNDRY_TOKEN` is accepted as a fallback for the token.
3. The `[default]` section of `~/.converge/config`:

   ```ini
   [default]
   hostname = https://converge.example.com/api
   token = <your token>
   ```

   Make that file readable by you only (`chmod 600 ~/.converge/config`).

The token is sent only as a bearer header to the host you configured. It never appears in a `repr()`, a log line or an error message. The client refuses HTTP redirects, so the token can never follow a redirect to another host.

```python
from converge_sdk import ConvergeClient

client = ConvergeClient()   # from the environment or ~/.converge/config
```

## Datasets

```python
ds = client.datasets.create("orders", parent_folder_rid="ri.example.folder.1")

with client.datasets.transaction(ds["rid"], "master", "APPEND") as tx:   # commits, or aborts on error
    tx.write_rows([{"id": 1, "total": 12.5}])
    tx.upload_file("more.csv", open("more.csv", "rb").read(), "text/csv")

for row in client.datasets.iterate_rows(ds["rid"], "master"):
    print(row)

rows = client.sql.execute("SELECT count(*) AS n FROM `/Project/orders`")   # list of dicts
```

The client also covers `get`, `iterate`, `delete`, `create_branch`, `list_branches`, `delete_branch`, `get_schema`, `put_schema`, `list_files`, `read_file` and `read_table` (one page, with an optional single-column filter).

## Ontologies, without generated code

```python
from converge_sdk import ActionConfig, ActionMode, prop

o = client.ontology("my-ontology")
big = o.objects("Order").where(prop("total") > 100).order_by(prop("total").desc()).take(10)
customer = o.objects("Order").linked("o1", "placedBy").get("c1")
o.action("place_order")(order_id="o9", action_config=ActionConfig(mode=ActionMode.VALIDATE_ONLY))
value = o.query("customer_lifetime_value")(customer_rid="customer/c1")
att = o.attachments.upload(b"...", "invoice.pdf", "application/pdf")
```

The where grammar has `==`, `<`, `<=`, `>`, `>=`, `in_`, `range`, `regex` and `is_null()`, combined with `&` and `|`. The server has no `not`, so `~`, `!=` and `is_null(False)` raise.

## Generated ontology packages

Your platform generates a typed package per ontology, with classes for your object types, keyword-checked actions and queries. That package depends on `converge-sdk` and contains only the types:

```python
from ontology_sdk import FoundryClient, Order   # names kept for existing code

client = FoundryClient("https://converge.example.com/api")   # or pass auth=UserTokenAuth(token)
client.ontology.objects.Order.where(Order.object_type.total > 5).take(10)
```

To install both from the platform's package index:

```sh
pip install --extra-index-url https://converge.example.com/api/v2/osdk/pypi/simple/ converge-osdk-<ontology>
```

## Not available yet

Dataset views, projections, retention policies, Iceberg tables, set operations on object sets, media properties, and the SQL job list. The SDK only calls routes the server has today.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2026 PT ANTERO DAEMON TEKNOLOGI.

## Security

Report vulnerabilities privately. See [SECURITY.md](SECURITY.md).
