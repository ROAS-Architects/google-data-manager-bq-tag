# Google Data Manager + BQ by ROAS Architects

A fork of
[`stape-io/google-conversion-events-tag`](https://github.com/stape-io/google-conversion-events-tag),
maintained by [ROAS Architects](https://roasarchitects.com), that keeps the
template's BigQuery logging in place.

Everything else is upstream's. The tag sends conversion events to Google Ads,
Campaign Manager 360, Search Ads 360, Display & Video 360 and Google Analytics
through the [Data Manager API](https://developers.google.com/data-manager/api),
exactly as it does upstream. This fork adds one thing: every request it sends
and every response it gets back are written to a BigQuery table you own.

## Why we forked this

Stape's template is good work, and it is Apache 2.0, which is why a fork like
this is possible at all. Between 2026-05-26 and 2026-07-01 they removed the
logging from their server-side tag fleet as part of a wider refactor. For this
template that is commit
[`330f7cc`](https://github.com/stape-io/google-conversion-events-tag/commit/330f7cc),
which took out the BigQuery path and the console path together. The template
ships with no logging at all today. For something that has to run in anybody's
container, dropping a path most installs never switch on is a fair call.

We need it, for a reason specific to how we work rather than a criticism of that
decision. A server-side tag fails quietly. There is no browser console to check
and no user to complain. On 2026-07-22 this exact tag returned HTTP 403 on every
offline conversion upload for twenty-six hours, and we found out a day late,
because it was the only tag in that container with no log table behind it. Its
siblings, still logging, we could simply query.

So this fork restores the logging by reverting that one commit, on top of
upstream's current tip. The GA4-events, Floodlight and email-normalization work
Stape shipped after the removal is all still here.

## What gets logged

This is the part upstream never wrote down, and the reason we keep the fork
rather than a private patch. If you install this template, you should be able to
read what lands in your table without reading the source.

### The table

Create it once, in a dataset the container can write to:

```sql
CREATE TABLE `your_project.your_dataset.your_table` (
  timestamp            INT64,
  tag_name             STRING,
  type                 STRING,
  trace_id             STRING,
  event_name           STRING,
  request_method       STRING,
  request_url          STRING,
  request_body         STRING,
  response_status_code INT64,
  response_headers     STRING,
  response_body        STRING
);
```

| Column | What goes in it |
| --- | --- |
| `timestamp` | Milliseconds since epoch, taken when the row is built, not when the request was sent |
| `tag_name` | Always `GoogleConversionEvent` for this template. Sibling tags write their own name, so one table can hold a whole container |
| `type` | `Request`, `Response`, or `Message` |
| `trace_id` | The container's `trace-id` request header, which joins a request row to its response row and to rows other tags wrote for the same event. **Only if your host sets that header.** Stape-hosted containers do; a self-hosted container behind your own proxy generally does not, and the column is then NULL for every tag, not just this one |
| `event_name` | Always `ConversionEvent` |
| `request_method` | Always `POST` |
| `request_url` | The ingest endpoint. Under the Stape auth flow this carries your container API key as a path segment, and we mask it to first four and last four characters, so you can tell two keys apart without holding either. Under Own Google Credentials it is Google's endpoint and carries nothing sensitive |
| `request_body` | The full `events:ingest` payload, as JSON |
| `response_status_code` | The API's HTTP status. Empty when the request never completed |
| `response_headers` | The API's response headers, as JSON |
| `response_body` | The API's response body. On a failed or timed-out request this instead holds the failure text, since there is no response to record |

> **The masking is our change, not upstream's behaviour.** The logging we
> restored recorded the endpoint verbatim, and under the Stape auth flow that
> endpoint contains a live credential. See below.

### When rows are written

Three log points:

1. **Request**, immediately before the call to the Data Manager API.
2. **Response**, when the call comes back, whatever the status. A 403 is a
   `Response` row with `response_status_code = 403` and Google's error in
   `response_body`. This is the row that makes a broken upload visible.
3. **Message**, when the request fails or times out, and when the tag refuses to
   send because required fields are missing or a session-attributes cookie is
   too large. The reason is in `response_body`.

### Things worth knowing before you rely on it

- **Logging is off unless you turn it on.** Set *BigQuery logging* to `Always`
  and fill in the project, dataset and table. There is no debug-only mode for
  BigQuery, unlike console logging.
- **BigQuery logging and console logging are independent.** Setting one does
  nothing to the other.
- **Optimistic mode suppresses nothing, but it does hide the outcome.** With
  *Use Optimistic Scenario* on, the tag still logs the response, but it calls
  `gtmOnSuccess()` before the reply arrives, so the container reports success
  whatever the API said. Leave it off if the tag's status should mean anything.
- **A tag that exits early logs nothing.** Consent denied produces no rows at
  all. An empty table means "nothing was sent", which is not the same as
  "nothing was received".
- **Rows are inserted with `ignoreUnknownValues`.** A column missing from your
  table does not raise an error, it silently drops that field. If a column looks
  permanently empty, check the table schema before you check the code.
- **Inserts are streamed.** Freshly written rows sit in the streaming buffer, so
  a query with a partition filter can miss the last few minutes.

## Enabling it

In the tag's *Logs Settings*:

| Field | Value |
| --- | --- |
| BigQuery logging | `Log to BigQuery` |
| BigQuery Table | `project.dataset.table` |

Write the table as `dataset.table` to take the project from the container's
`GOOGLE_CLOUD_PROJECT` environment variable, which on Google Cloud is already
set to the project's ID.

Upstream's logging used three separate boxes for project, dataset and table.
One box does the same job, and it has to, for the reason in the next section.

The container needs write access to that table. On Stape-hosted containers this
is wired for you. Self-hosted, the sandboxed BigQuery API resolves application
default credentials, so the container's own service account needs
`bigquery.tables.updateData` on the table. Streaming inserts do not need the
BigQuery Job User role.

## The 100-field limit, and what we spent to get under it

Google caps a custom template at **100 fields**, counting groups and labels
alongside inputs. Over that, the Tag Manager API refuses to create the template
at all: *"You have reached the maximum number of fields allowed."* Upstream's
current tip sits at exactly 100. Restoring the logging the way it was written
would have cost 6 more, and nobody could have installed the result.

So the logging is built to be cheap, and we bought the rest:

- **Two fields, not six.** A `Log to BigQuery` switch and one `BigQuery Table`
  box holding `project.dataset.table`. Upstream's version wrapped three separate
  boxes in two nested groups, and in this template a group costs a field like
  anything else.
- **Three labels folded into help text.** `help` is a property of a field, not a
  field of its own, so the guidance on request-level consent, on user-data
  identifiers, and on the address fields now sits under the first input of each
  section instead of above it. Not a word of it was dropped.

That leaves the template at **99 fields**, and CI fails if a rebase pushes it
over. There is more room if we ever need it: ten groups in this template wrap
exactly one child, and each is a spare field. We would rather leave them alone,
because every one is a conflict on the next upstream rebase.

## Three changes we made while restoring it

All three are visible in the diff against the last upstream version that carried
logging.

1. **Failure text is written to `response_body`.** The original failure path put
   its diagnostics in fields called `Message` and `Reason`. Neither has a
   column, so with `ignoreUnknownValues` a timeout landed a row with the
   diagnostics gone and every response field empty. Folding the text into
   `response_body` keeps it, and `response_body` is empty on exactly that path.
2. **The container API key in `request_url` is masked.** Under the Stape auth
   flow the endpoint is
   `https://{identifier}.{domain}/stape-api/{key}/v2/data-manager/events/ingest`,
   so the key is a path segment. The original logging recorded that endpoint as
   it was built, so restoring it unchanged would have put a live credential in
   every Request row, and in any console output pasted into a support thread. We
   mask it to `abcd...WXYZ`, keeping four characters at each end so two keys are
   still distinguishable, and mask anything twelve characters or shorter whole.
   Masking happens once, in `log()`, so it covers every destination and any log
   point added later. The request itself is unchanged and still carries the real
   key.
3. **Values that are already strings are not stringified again.**
   `sendHttpRequest` hands back `result.body` as a string, and stringifying it a
   second time wraps it in escaped quotes, which stops `JSON_VALUE()` from
   parsing rows that parse fine for other tags writing to the same table.

## How this fork tracks upstream

- `upstream-mirror` is a plain mirror of `stape-io/google-conversion-events-tag`.
  We never commit to it.
- `main` is `upstream-mirror` plus the restored logging. So
  `git diff upstream-mirror..main` is the whole of what we changed, and is the
  only fork documentation there is. The template sits on `main` because the
  Community Gallery requires every resource to be on that branch.
- Following an upstream release: fetch upstream, fast-forward `upstream-mirror`,
  then rebase `main` onto it. We sync when we want something upstream has
  shipped, not on a schedule.
- After editing `template.js`, run `python3 scripts/sync-tpl.py` to copy it into
  `template.tpl`. GTM only ever runs the embedded copy.
- CI checks that `template.tpl`'s embedded JS still matches `template.js`, that
  the logging is still there, that the masking still masks, that the table
  parsing still parses, and that the template is still under 100 fields. Those
  are the ways a rebase can quietly undo the entire point of this repo.

If you do not query your tag logs, install upstream's template. It is the same
tag, with less to configure. This fork is for people who want the send path on
the record.

---

# Upstream documentation

Everything below describes the tag itself, and is upstream's, unchanged apart
from the two footer sections.

## How to use the Google Data Manager API Conversion Events Tag

1.  Choose the authentication method:
    *  **Stape Google Connection (recommended)**: sign in to the Data Manager API Connection via the Stape admin. This is the easiest way to set up the authentication. [How-to](https://stape.io/solutions/data-manager-api-connection).
    *  **Own Google Credentials**: a [Service Account impersonation](https://developers.google.com/data-manager/api/devguides/quickstart/set-up-access?credential_type=service_account) is the simplest way to handle the authentication when using the **Own Google Credentials** method.
        > ℹ️ **CM, DV and SA 360 (Floodlight)** and **Google Analytics (GA4)** destinations are only available with the **Own Google Credentials** authentication method.

        To configure it correctly, you must:
       1) Enable the Data Manager API in a GCP Project.
       2) Create a Service Account in this GCP Project.
       3) Add the `Service Account Token Creator IAM` role (`roles/iam.serviceAccountTokenCreator`) to the Service Account.
       4) Generate a `JSON Key` from this Service Account ([how-to](https://docs.cloud.google.com/iam/docs/keys-create-delete#creating)) and download it.
       5) Connect the Service Account to the container using the `JSON Key` file:
          - If hosting on Stape, [use the **Service Account power-up**](https://stape.io/blog/how-to-connect-google-service-account-to-stape).
          - If NOT hosting on Stape, follow [these instructions](https://developers.google.com/tag-platform/tag-manager/server-side/manual-setup-guide#optional_include_google_cloud_credentials).
       6) Grant the Service Account access to the product you're interacting with (Google Ads account, CM360 account, Google Analytics property etc.).

2.  Add the tag to your server container in GTM. This fork is **Google Data Manager + BQ** in the Community Template Gallery, under ROAS Architects; upstream's original is [Google Data Manager API Conversion Events](https://tagmanager.google.com/gallery/#/owners/stape-io/templates/google-conversion-events-tag), under stape-io.
3.  Choose the **Event Type**: `Conversion` or `Pageview`.
    1.  `Pageview`
    2.  `Conversion`
        1.  Set up your **Destination Accounts and Conversion Events**, specifying the Advertising Accounts Customer IDs and the corresponding Conversion Event IDs you want to send data to.
        2.  Choose your **Conversion Event Mode**: `Single` to configure one event's data through the UI, or `Multiple` to manually provide a pre-formatted array of events.
        3.  Configure the **Conversion Information**, **User Data**, and other relevant parameter groups. The tag can auto-map many of these fields from a standard GA4 or e-commerce data layer.
            > ❗ If using Enhanced Conversions (user email address, user phone number etc.), ensure you do the following in Google Ads (_Goals > Conversions > Settings_) or CM360. These settings must be active for the destination account and its manager (MCC) account, if applicable:
            >    1.  Accept the [Customer Data Terms](https://support.google.com/adspolicy/answer/7475709).
            >    2.  Enable **Enhanced Conversions** and **Enhanced Conversions for Leads**.
        4.  Add a trigger to fire the tag on the appropriate server-side events (e.g., a `page_view` event or a `purchase` event).

## Event Types

### Pageview
This mode sets the `_dm_session_attributes` cookie containing a base64 JSON encoded string with the *Session Attributes* values for conversion event attribution and modeling.
-   **Default mappings**:
    -   Session Attribute `gad_source`: `gad_source` URL Parameter value
    -   Session Attribute `gad_campaignid`: `gad_campaignid` URL Parameter value
    -   Session Attribute `landing_page_url`: `page_location` Event Data value
    -   Session Attribute `landing_page_referrer`: `page_referrer` Event Data value
    -   Session Attribute `landing_page_user_agent`: `user_agent` Event Data value
    -   Session Attribute `session_start_time_usec`: current timestamp of the time when the Pageview tag set the cookie

### Conversion
This mode sends the conversion event.

---

#### Destination Accounts and Conversion Events
This is where you define which advertising accounts and specific conversion actions will receive the data.
-   **Product**: The Google product to send data to. Currently supports **Google Ads**, **CM, DV and SA 360 (Floodlight)**, and **Google Analytics (GA4)** (the latter two, only for the `Own Google Credentials` authentication method).
-   **Operating Customer ID**: The Account ID (without hyphens) of the account that will receive the conversion events.
    -   **Google Ads**: this is your Google Ads Account ID (without hyphens).
    -   **CM360**: this is the [Advertiser ID](https://support.google.com/campaignmanager/answer/11568119?hl=en).
    -   **Google Analytics**: this is the [Property ID](https://developers.google.com/analytics/devguides/reporting/data/v1/property-id#google_analytics).
-   **Customer ID**: The Account ID (without hyphens) of the account used for authorization when making the API request.
    -   **Google Ads**: if your credentials belong to an MCC account that manages the Operating Account, set this to the MCC Account ID. If your credentials belong directly to the Operating Account, you can leave this field empty.
    -   **CM360**: this is also the [Advertiser ID](https://support.google.com/campaignmanager/answer/11568119?hl=en). If your credentials are for a Manager Account that manages the Operating Account, set this to the Manager Account ID.
    -   **Google Analytics**: this is also the [Property ID](https://developers.google.com/analytics/devguides/reporting/data/v1/property-id#google_analytics), and you can leave it blank.
-   **Conversion Event ID**: The ID of the specific conversion action to receive data.
    -   **Google Ads**: navigate to *Google Ads account > Goals > Conversions > Summary* and click on the desired Conversion Action. The ID is the value of the `ctId` query parameter in your browser's URL. [Learn more](https://developers.google.com/data-manager/api/devguides/concepts/destinations#ads-event).
    -   **CM360 (Floodlight)**: this is the **Floodlight Activity ID**. Find it on the *Activities* page — the ID is the number shown next to the activity name in the Activity name column. [Learn more](https://developers.google.com/data-manager/api/devguides/concepts/destinations#floodlight-event).
    -   **Google Analytics**: this is the [Measurement ID](https://support.google.com/analytics/answer/12270356) (for web streams) or the [Firebase App ID](https://developers.google.com/data-manager/api/devguides/concepts/destinations#ga-event) (for app streams).

> ❗ **CM360 service account permissions**: the service account used for authentication must have a user role with the **Insert offline conversions** permission granted in CM360. [Learn more](https://developers.google.com/data-manager/api/devguides/concepts/destinations#cm3-credentials).

---

#### Conversion Event Mode
You can send data in two ways:
-   **Single Conversion Event**: Configure the parameters for a single conversion directly in the tag's UI fields.
-   **Multiple Conversion Events**: Provide a complete, pre-formatted JSON array containing data for up to 2000 conversion events. This is useful for batch uploads.

---

#### Conversion Information
This section contains the core details of the conversion.
-   **Parameters**: Includes `Event Source`, `Transaction/Order ID`, `Event Timestamp`, `Currency`, and `Conversion Value`.
    -   **Event Source**: a signal for where the event happened originally (`WEB`, `APP`, `IN_STORE`, `PHONE`, or `OTHER`). GA4 events only support `WEB` and `APP`.
    -   **Auto-mapping**: If enabled, the tag will attempt to automatically populate these fields from the incoming event data (e.g., `transaction_id`, `currency`, `value`).
-   **Google Analytics Required Data** (`Own Google Credentials` only): a table to set fields required when Google Analytics (GA4) is a destination — `Event Name` (required), `User ID`, `Client ID` (required for web streams), and `App Instance ID` (required for app streams).

---

#### User Data
This section is crucial for matching the conversion to a user. You can provide multiple identifiers to improve match rates.
-   **Identifiers**: Includes `Email Address(es)`, `Phone Number(s)`, and `User Address` (First Name, Last Name, Region, Postal Code).
    -   **Auto-mapping**: If enabled, the tag will automatically pull user data from common event data keys (e.g., `user_data.email`).
-   **Hashing & Normalization**: The tag automatically normalizes and SHA-256 hashes user identifiers if they are provided in plain text, following Google's formatting guidelines.

---

#### Ad Identifiers
This section allows you to send click identifiers for attribution. It's as important as the User Data parameters for matching the conversion to a user.
-   **Click IDs**: `gclid`, `gbraid`, `wbraid` and `dclid` (for Floodlight). `gclid` can also be used for Google Analytics (GA4) events sent as an additional data source. [Learn more](https://developers.google.com/data-manager/api/devguides/events/analytics/online).
    -   **Auto-mapping**: If enabled, the tag will automatically pull Click IDs from, in this order, Event Data > URL Parameter > Server Cookie > JavaScript Cookie.
-   **Other Floodlight-specific Identifiers** (`Own Google Credentials` only): `Match ID`, `Impression ID`, and `Encrypted User ID`.
-   **Landing Page Parameters and Session Attributes**: `Landing Page User Agent`, `Landing Page IP Address` and `Session Attributes`
    -   **Auto-mapping**: If enabled, the tag will automatically pull Session Attributes from, in this order: `session_attributes` Event Data value > `_dm_session_attributes` Common Cookie value > `_dm_session_attributes` cookie set by the Pageview event of this tag.

> Note: for **Google Ads** and **Floodlight** destinations, at least one Ad Identifier or User Data value must be specified. For **Google Ads**, the Device Information `IP Address` (below) also counts as a valid identifier, except for `IN_STORE` events.

---

#### Device Information
You can include device details for the conversion event.
-   **Parameters**: `User Agent` and `IP Address`.

---

#### User Properties
This section provides more context about the customer.
-   **Parameters**: `Customer Type` (New, Returning, or Re-engaged) and `Customer Value Bucket` (Low, Medium, or High).
-   **Google Analytics User Properties** (`Own Google Credentials` only): a table to send additional [user properties](https://developers.google.com/analytics/devguides/collection/protocol/ga4/user-properties) as `User Property Name`/`User Property Value` pairs.

---

#### Cart Data
This section allows for sending product-level details for e-commerce transactions.
-   **Parameters**: `Merchant Center ID`, `Feed Label`, `Feed Language Code`, `Transaction Discount`, and a list of `Items` with their `Item ID`, `Merchant Product ID`, `Item Quantity`, and `Price`.
    -   **Auto-mapping**: If enabled, the tag will automatically pull `Items` from Event Data.
-   **Add other Item Parameters**: If enabled, any item property that isn't `Item ID`, `Merchant Product ID`, `Item Quantity`, or `Price` is also sent per item as `additionalItemParameters` (used by Google Analytics) and `customVariables` (used by Google Ads and Floodlight).

> Note: it's **required** to send at least the **Item ID** or the **Merchant Product ID** for each item.

---

#### Custom Variables
This section allows you to send any additional key-value pairs for custom reporting.
-   **Parameters**: A list of `Variable ID`, `Variable Value`, and optional `Destination References`.

##### How to obtain the `Variable ID`
<details>
    <summary>⬇️ Click to expand ⬇️</summary>
    <br/>

There are 2 simple ways to obtain the Custom Variable ID.

**1 - Using Scripts in Google Ads UI**

1. Open Google Ads.
2. Go to _Tools > Bulk Actions > Scripts_. Tip: use the search bar at the top.
3. Click the `+` button to a new script and give it a descriptive name.
4. Paste this code in the script code block:
```js
function main() {
const query = `
    SELECT
    conversion_custom_variable.id,
    conversion_custom_variable.name,
    conversion_custom_variable.tag,
    conversion_custom_variable.status
    FROM conversion_custom_variable
`;

const searchResults = AdsApp.search(query);

console.log('------------------------------------------------------------------------------------------------------');
console.log('# CUSTOM VARIABLES INFORMATION #');
console.log('------------------------------------------------------------------------------------------------------');
console.log(
    'NAME'.padEnd(30) + ' | ' +
    'TAG STRING'.padEnd(20) + ' | ' +
    'STATUS'.padEnd(18) + ' | ' +
    'ID (Use this in GTM!)'
);
console.log('------------------------------------------------------------------------------------------------------');

let count = 0;
while (searchResults.hasNext()) {
    const row = searchResults.next().conversionCustomVariable;
    const status = row.status;
    const name = row.name.padEnd(30);
    const tag = row.tag.padEnd(20);
    const id = row.id;
    console.log(`${name} | ${tag} | ${status.padEnd(18)} | ${id}`);
    count++;
}

if (count === 0) console.log('No custom variables found in this account.');

console.log('------------------------------------------------------------------------------------------------------');
}
```
5. Give it the requested permissions through the `Authorize` button.
6. Click `Preview`. There's no need to click `Run`.
7. Go to the `Logs` tab. This is where the **Custom Variable ID** will show up.

    Example:

    ![Google Ads script logs](https://github.com/user-attachments/assets/018a102c-53d2-4476-aa95-c15ea0cdbebd)

8. Use the **Custom Variable ID** in the `Variable ID` field of the tag **Custom Variables** section.

**2 - Using DevTools**

1. Open Google Ads.
2. Go to _Goals > Conversions > Custom Variables_. Tip: use the search bar at the top.
3. Open DevTools and go to the Network tab.
4. In the Network tab, search for `ConversionCustomVariableService/List`.
6. Reload the Custom Variables page.
7. The Network panel should display a request (filtered by the filter added in step 4).
8. Click on this request and go to the `Response` tab.
9. The Custom Variable information will be in the array value of the key named `"1"`. Each item in the array is a custom variable.
10. The **Custom Variable ID** is the key `"1"` inside the object. The Custom Variable Name is the key `"4"`.

    Example:

    ![Google Ads DevTools](https://github.com/user-attachments/assets/47c3001b-51aa-40bc-b11f-04d3c3654ef8)

11. Use the **Custom Variable ID** in the `Variable ID` field of the tag **Custom Variables** section.
</details>

---

#### Google Analytics Event Parameters
Available only for the `Own Google Credentials` authentication method.
This section lets you send any [GA4 event parameters](https://developers.google.com/data-manager/api/reference/analytics/recommended-events) that aren't captured by the other fields (e.g., `tax`, `shipping`).
-   **Parameters**: A list of `Field Name` and `Field Value` pairs.

---

### Advanced Options

* **Validate Only**: If `true`, the request is validated by the API but not executed. This is useful for debugging.
* **Use Optimistic Scenario**: If `true`, the tag fires `gtmOnSuccess()` immediately without waiting for a response from the API. This speeds up container response time but may hide downstream errors.
* **Request-level Consent**: Apply `adUserData` and `adPersonalization` consent statuses to all users in the request. This can be overridden at the user level when using the "Multiple Users" mode.
* **Consent Settings**: Prevent the tag from firing unless the necessary ad storage consent is granted by the user.
* **Logging**: Configure console and/or BigQuery logging for debugging and monitoring requests and responses.

## Useful Resources
* [Step-by-step guide on how to configure Google Data Manager API Conversion Events Tag](https://stape.io/helpdesk/documentation/configure-google-conversion-events-tag)
* [Stape's Data Manager API Connection](https://stape.io/solutions/data-manager-api-connection)
* [Data Manager API for Conversion Events](https://developers.google.com/data-manager/api/reference/rest/v1/events)
* [Conversion Event definition](https://developers.google.com/data-manager/api/reference/rest/v1/events/ingest#Event)
* [User Identifiers Normalization Guidelines](https://developers.google.com/data-manager/api/get-started/formatting)
* Session Attributes: [[1]](https://support.google.com/google-ads/answer/16194756?hl=en) and [[2]](https://developers.google.com/data-manager/api/reference/rest/v1/events/ingest#AdIdentifiers)

## Open Source

The **Google Data Manager API Conversion Events Tag for GTM Server-Side** is
developed and maintained by the [Stape Team](https://stape.io/) under the Apache
2.0 license. This fork is maintained by
[ROAS Architects](https://roasarchitects.com) under the same license, and is not
affiliated with or endorsed by Stape.
