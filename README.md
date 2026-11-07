
# njlea-api

This is the source code for the NJ Law Enforcement Agencies API deployed
at `api.tor-gu.com/nj/lea/`.

It serves [njlea](https://github.com/tor-gu/njlea), a registry of New
Jersey law enforcement agencies from 2020 to 2026. Each agency has a
stable ID, its names over time, its level of government and function,
the municipalities it polices, its FBI ORIs, and every spelling of it
used by the NJ Office of the Attorney General (OAG) datasets. Field
names and values are the same as in the R package; see it for more
details on the underlying dataset.

## Try it out

### OpenAPI/Swagger

There is an OpenAPI/swagger document deployed
[here](https://tor-gu.com/apis/njlea.html) that you can play with. The
spec is `njlea-openapi.yaml`.

### Endpoints

| Endpoint                                                                | R equivalent                                  | Filters                                     |
|-------------------------------------------------------------------------|-----------------------------------------------|---------------------------------------------|
| `/nj/lea/agencies`, `/nj/lea/agencies/{year}`                           | `get_agencies(year)`                          | `county`, `agency_level`, `agency_function` |
| `/nj/lea/agencies/{year}/{agency_id}`                                   | one row of `get_agencies(year)`               |                                             |
| `/nj/lea/agency_epochs`                                                 | the `agency` table                            | `agency_id`                                 |
| `/nj/lea/agency_municipalities`, `/nj/lea/agency_municipalities/{year}` | `get_agency_municipalities(year, geoid_year)` | `geoid_year`, `agency_id`, `GEOID`          |
| `/nj/lea/aliases`                                                       | the `agency_alias` table                      | `source`, `agency_id`                       |
| `/nj/lea/oris`, `/nj/lea/oris/{ori}`                                    | the `agency_ori` table                        | `agency_id`                                 |
| `/nj/lea/sources`                                                       | the `alias_source` table                      |                                             |
| `/nj/lea/search?q=`                                                     | `find_agency(pattern, county, year)`          | `county`, `year`                            |

Without a `{year}`, the latest year (2026) is used, and the reply’s
links give it explicitly. `county` may be given as `Camden` or
`Camden County`.

### Sample code

Each endpoint returns paginated results, with a `"next"` url in the
`"links"` section indicating that there are more results to be
retrieved.

This is illustrated in the python code below, which loads the agencies
of 2026 into a [pandas
DataFrame](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.html)
and counts them by level.

``` python
import json
import requests
import pandas as pd

API_ROOT = r.API_ROOT


def load_as_df(url):
    """Retrieve entire dataset at url and return as a dataframe"""
    # Get the first page
    resp = requests.get(url)
    resp.raise_for_status()
    resp_json = json.loads(resp.content.decode('utf-8'))
    df = pd.DataFrame(resp_json["data"])

    # Keep retrieving pages while there is a 'next' link
    while "next" in resp_json["links"]:
        resp = requests.get(resp_json["links"]["next"])
        resp.raise_for_status()
        resp_json = json.loads(resp.content.decode('utf-8'))
        df = pd.concat([df, pd.DataFrame(resp_json["data"])], ignore_index=True)
    return df


agencies_2026 = load_as_df(f"{API_ROOT}/nj/lea/agencies/2026")
by_level = agencies_2026.groupby("agency_level").size().reset_index(name="n")
```

| agency_id | agency_name                                 | county          | agency_level | agency_function | multi_municipal |
|:----------|:--------------------------------------------|:----------------|:-------------|:----------------|:----------------|
| NJLEA0001 | Absecon Police Department                   | Atlantic County | Municipal    | Police          | FALSE           |
| NJLEA0002 | Atlantic City Police Department             | Atlantic County | Municipal    | Police          | FALSE           |
| NJLEA0003 | Atlantic County Division of Adult Detention | Atlantic County | County       | Corrections     | FALSE           |
| NJLEA0004 | Atlantic County Prosecutor’s Office         | Atlantic County | County       | Prosecutor      | FALSE           |
| NJLEA0005 | Atlantic County Sheriff’s Office            | Atlantic County | County       | Sheriff         | FALSE           |
| NJLEA0006 | Brigantine Police Department                | Atlantic County | Municipal    | Police          | FALSE           |

| agency_level    |   n |
|:----------------|----:|
| Bi-state        |   3 |
| County          |  60 |
| Municipal       | 458 |
| Private         |   3 |
| School district |   1 |
| State           |  18 |

#### Agencies serving several municipalities

`multi_municipal` is `true` for an agency linked to more than one
municipality in the year. It is `false` for agencies with no links at
all, too: sheriffs, prosecutors, state agencies and the NJ State Police.

``` python
multi = agencies_2026[agencies_2026["multi_municipal"]]
```

|     | agency_id | agency_name                           | county            | agency_level | agency_function | multi_municipal |
|:----|:----------|:--------------------------------------|:------------------|:-------------|:----------------|:----------------|
| 131 | NJLEA0132 | Camden County Police Department       | Camden County     | County       | Police          | TRUE            |
| 143 | NJLEA0144 | Haddon Township Police Department     | Camden County     | Municipal    | Police          | TRUE            |
| 164 | NJLEA0166 | Cape May Police Department            | Cape May County   | Municipal    | Police          | TRUE            |
| 210 | NJLEA0212 | Franklin Township Police Department   | Gloucester County | Municipal    | Police          | TRUE            |
| 224 | NJLEA0227 | Woodbury Police Department            | Gloucester County | Municipal    | Police          | TRUE            |
| 225 | NJLEA0228 | Woolwich Township Police Department   | Gloucester County | Municipal    | Police          | TRUE            |
| 304 | NJLEA0307 | Belmar Police Department              | Monmouth County   | Municipal    | Police          | TRUE            |
| 351 | NJLEA0355 | Chester Township Police Department    | Morris County     | Municipal    | Police          | TRUE            |
| 383 | NJLEA0388 | Washington Township Police Department | Morris County     | Municipal    | Police          | TRUE            |
| 384 | NJLEA0389 | Wharton Police Department             | Morris County     | Municipal    | Police          | TRUE            |

#### Municipalities served

A municipal department’s own municipality is its `Home` link; a
municipality it polices by agreement is a `Service` link. Camden County
Police Department polices Camden city, and took over Woodlynne in 2024
when the Woodlynne Police Department disbanded:

``` python
camden = load_as_df(f"{API_ROOT}/nj/lea/agency_municipalities/2025?agency_id=NJLEA0132")
```

| agency_id | GEOID      | municipality      | county        | link_type |
|:----------|:-----------|:------------------|:--------------|:----------|
| NJLEA0132 | 3400710000 | Camden city       | Camden County | Service   |
| NJLEA0132 | 3400782450 | Woodlynne borough | Camden County | Service   |

`GEOID` is a US Census GEOID as of `geoid_year` (by default, the year),
so it joins to
[njmunicipalities-api](https://tor-gu.com/apis/njmunicipalities.html).
Here are the municipalities of 2026 with no agency link. **NJ State
Police links are not included yet**: NJSP is the local police of many
rural municipalities, but no published list names them, so most of these
are NJSP-patrolled, though not all.

``` python
links_2026 = load_as_df(f"{API_ROOT}/nj/lea/agency_municipalities/2026")
municipalities_2026 = load_as_df(f"{API_ROOT}/nj/municipalities/2026")
unlinked = municipalities_2026[~municipalities_2026["GEOID"].isin(links_2026["GEOID"])]
unlinked_by_county = unlinked.groupby("county").size().reset_index(name="n")
```

| county            |   n |
|:------------------|----:|
| Atlantic County   |   6 |
| Bergen County     |   2 |
| Burlington County |   9 |
| Camden County     |   1 |
| Cape May County   |   3 |
| Cumberland County |  11 |
| Gloucester County |   3 |
| Hunterdon County  |  11 |
| Mercer County     |   1 |
| Middlesex County  |   1 |
| Monmouth County   |   7 |
| Morris County     |   1 |
| Ocean County      |   2 |
| Salem County      |   8 |
| Somerset County   |   2 |
| Sussex County     |  13 |
| Warren County     |  12 |

#### Finding an agency

`/nj/lea/search` searches canonical names and every source spelling. `q`
is a case-insensitive substring, not a regular expression (unlike
`find_agency()` in the R package). Here a former name finds the Youth
Justice Commission, which was the Juvenile Justice Commission until
March 2025:

``` python
hits = load_as_df(f"{API_ROOT}/nj/lea/search?q=juvenile%20justice")
epochs = load_as_df(f"{API_ROOT}/nj/lea/agency_epochs?agency_id=NJLEA0539")
```

| agency_id | agency_name                         | county | matched_on      | matched_text                           |
|:----------|:------------------------------------|:-------|:----------------|:---------------------------------------|
| NJLEA0539 | New Jersey Youth Justice Commission | NA     | name            | New Jersey Juvenile Justice Commission |
| NJLEA0539 | New Jersey Youth Justice Commission | NA     | njoag-leod-2021 | Juvenile Justice Commission            |
| NJLEA0539 | New Jersey Youth Justice Commission | NA     | njoaguof        | NJ Juvenile Justice Commission         |

| agency_id | first_year | final_year | agency_name                            |
|:----------|-----------:|-----------:|:---------------------------------------|
| NJLEA0539 |       2020 |       2024 | New Jersey Juvenile Justice Commission |
| NJLEA0539 |       2025 |        NaN | New Jersey Youth Justice Commission    |

#### Joining to FBI data

ORIs are attributes, not keys: an agency can have several (the NJ State
Police has 22) or none. Join them to FBI Crime Data Explorer data on
`ori`:

``` python
rutgers = load_as_df(f"{API_ROOT}/nj/lea/oris?agency_id=NJLEA0543")
```

| agency_id | ori       | GEOID_Y2K  | first_year | final_year | match | note                                             |
|:----------|:----------|:-----------|-----------:|:-----------|:------|:-------------------------------------------------|
| NJLEA0543 | NJ0043900 | 3400710000 |       2020 | NA         | Hand  | CDE NJ list: ‘Rutgers University: Camden’        |
| NJLEA0543 | NJ0073000 | 3401351000 |       2020 | NA         | Hand  | CDE NJ list: ‘Rutgers University: Newark’        |
| NJLEA0543 | NJ0123000 | 3402351210 |       2020 | NA         | Hand  | CDE NJ list: ‘Rutgers University: New Brunswick’ |

## Deploying

This API is implemented as an [AWS
SAM](https://aws.amazon.com/serverless/sam/) application: one Lambda
function serves every route, with the data packaged in it. A deployment
has three parts:

1.  The lambda layer
    [layer_torguapi](https://github.com/tor-gu/layer_torguapi) (version
    11 or later), which needs to be deployed separately.
2.  The data: CSV exports of a tagged
    [njlea](https://github.com/tor-gu/njlea) release, committed in
    `data/`, and built into `lea/data/njlea.json` by `make data`.
3.  The Lambda and API Gateway, defined in `template.yaml`.

### Data

`data/` holds the njlea tables, the njmunicipalities rows they
reference, and `SOURCE`, which records the releases they were exported
from. The export also writes R’s own `get_agencies()` and
`get_agency_municipalities()` for every year and `geoid_year` to
`tests/parity/expected/`, which the parity test requires the API to
reproduce. To export a release (this needs R and the `remotes` package;
the release is installed into a temporary library) and build the
Lambda’s data:

    make export_data REF=v0.1.0
    make data

`lea/data/njlea.json` is not committed; CI builds it with `make data`
before testing and before `sam build`.

### Data update

1.  `make export_data REF=<new release>`, and review the diff in
    `data/`.
2.  `make data parity_test example_test`. The year range and the default
    year come from the export, but the spec’s examples, its year ranges
    and this README (then `make knit`) may need updating; the example
    test shows the new values.
3.  Push to `dev`, check the dev API, then merge to `main`.

### Development

    make venv          # .venv with the test, style and spec tools
    make style unit_test
    make data example_test parity_test
    make apigateway_spec   # the spec for API Gateway, without examples

The unit tests import the torguapi layer from `./torguapi`;
`scripts/fetch_torguapi.sh` downloads it.

### Direct deploy

The application can be deployed directly using the SAM CLI:

    make data apigateway_spec
    sam build
    sam deploy --stack-name MyStackName                                                         \
               --capabilities CAPABILITY_IAM                                                    \
               --resolve-s3                                                                     \
               --parameter-overrides                                                            \
                    TorguapiLayerArn=arn:aws:lambda:us-east-1:123456789012:layer:layer_torguapi \
                    TorguapiLayerVersion=10                                                     \
                    ApiRoot=https://api.example.com                                             \
                    DataVersion=$(sed -n 's/^version=//p' data/SOURCE)

Replace the `TorguapiLayerXXX` params with the values derived from the
`layer_torguapi` deployment.

The `ApiRoot` value is used only for generating the values in `"links"`
in the JSON reply. On `api.tor-gu.com`, the relationship between the
publicly facing API URL and the API Gateway endpoints is configured in
[torgu-api-cloudfront](https://github.com/tor-gu/torgu-api-cloudfront).

To deploy a second environment alongside the first, give it a resource
name prefix (I use `dev-`) with the `EnvPrefix` template parameter.

### Using GitHub Actions

`.github/workflows/deploy.yml` deploys from GitHub: a push to `dev`
deploys the dev stack and runs the integration tests against it, and a
merge to `main` deploys prod. It assumes AWS roles through GitHub’s OIDC
provider; the roles are defined in `infra/github/` (Terraform).
