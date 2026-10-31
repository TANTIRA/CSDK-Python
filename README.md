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

The token is sent only as a bearer header to the host you configured. It never appears in a `repr()`, a log line or an error message. The client refuses HTTP redirects, so the token can never follow a redirect to another host. It also refuses a plain-http base URL, except for `localhost`, `127.0.0.1` and `[::1]`, and a base URL with a user name or password in it.

Pass `auth=lambda: get_fresh_token()` instead of `token` to fetch a token per request. A token with a space or line break (a trailing newline from a file, say) is refused with a `ConfigError` before anything is sent.

```python
from converge_sdk import ConvergeClient

client = ConvergeClient()   # from the environment or ~/.converge/config
```

A generated package's `FoundryClient()` takes no arguments the same way. The client uses the standard `HTTPS_PROXY` and `NO_PROXY` variables, and the system's certificate store for TLS.

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

### Media properties

A media reference property names an item in a media set. In a generated package it is a `Media`; without generated code, read it with `o.media.get(object_type, primary_key, property)`:

```python
photo = o.media.get("Order", "o1", "photo")
data = photo.get_media_content()        # bytes
meta = photo.get_media_metadata()       # .path, .size_bytes, .media_type
ref = photo.get_media_reference()       # the MediaReference the property holds

ref = o.media.upload("Order", "photo", png_bytes, media_item_path="orders/o9.png")
o.action("set_photo")(order_id="o9", photo=ref)   # an action writes it to the property
```

The server checks the object and the media set before it answers. The content is untrusted, because the uploader chose its type. Showing an image, video or audio in an `<img>`, `<video>` or `<audio>` element is fine; never open other content (HTML, SVG) as a `blob:` or `data:` URL in a frame, tab or link, where it would run on your app's origin.

The where grammar has `==`, `<`, `<=`, `>`, `>=`, `in_`, `range`, `regex`, `starts_with`, `is_null()` and the text search methods `contains_any_term`, `contains_all_terms`, `contains_all_terms_in_order` and `contains_all_terms_in_order_prefix_last_term` (whole words, case-insensitive), combined with `&` and `|`. `== None` is `is_null()`. `~` negates a clause; `!=` and `is_null(False)` are negations too, so `!=` also matches objects with no value. On one object type, `|` is a union, `&` an intersection, and `a & ~b` subtracts `b` from `a`. Pages hold 1 to 1000 objects; use `page`, `iterate`, `take` or `list` (every object). `aggregate()` returns the server's answer as a dict, so there is nothing to convert.

```python
from converge_sdk.ontologies import duration, max_group_count, metric

o.objects("Order").aggregate(
    metrics=[metric("count"), metric("sum", prop("total"), "total")],
    group_by=[duration(prop("placed_at"), 1, "MONTHS"), max_group_count(prop("status"), 5)],
    order=("total", "desc"),
)
```

Time buckets are in UTC, weeks start on Monday, and months, quarters and years follow the calendar. `max_group_count` keeps the largest groups and marks the answer `APPROXIMATE`. An aggregate may produce at most 10,000 groups.

`o.objects("Doc").nearest_neighbors(embedding, 10, "embedding")` returns the objects whose vector property is closest to `embedding` (exact cosine similarity, as `$score`, best first), among the objects you may read; the set's filter applies. The query must have exactly the property's `vectorDimension` numbers, and `num_neighbors` is 1 to 500.

## Generated ontology packages

Your platform generates a typed package per ontology, with classes for your object types, keyword-checked actions and queries. That package depends on `converge-sdk` and contains only the types:

```python
from ontology_sdk import FoundryClient, Order   # names kept for existing code

client = FoundryClient("https://converge.example.com/api")   # or pass auth=UserTokenAuth(token)
client.ontology.objects.Order.where(Order.object_type.total > 5).take(10)
```

To install both from the platform's package index, use **`--index-url` only**:

```sh
pip install --index-url "https://__token__:$CONVERGE_TOKEN@converge.example.com/api/v2/osdk/pypi/simple/" converge-osdk-<ontology>
```

The user name is always `__token__`; the password is your token. To keep it out of your shell history, put `machine converge.example.com login __token__ password <your token>` in `~/.netrc` and leave it out of the URL.

Do not add `--extra-index-url` for public PyPI in the same install. pip would then also look up `converge-sdk` and `converge-osdk-*` on PyPI, and whoever registered those names there could run code on your machine. The platform index serves everything the package needs.

## Not available yet

Dataset views, projections, retention policies, Iceberg tables, set operations across object types, and the SQL job list. The SDK only calls routes the server has today.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2026 PT ANTERO DAEMON TEKNOLOGI.

## Security

Report vulnerabilities privately. See [SECURITY.md](SECURITY.md).
