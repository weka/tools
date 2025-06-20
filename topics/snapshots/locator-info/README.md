# Locator Info Script

Parse and display the data of a spec file of an uploaded snapshot.

## Basic Idea

Sometimes it's convenient to view details about a locator of an uploaded snapshot without requiring a weka cluster. This script makes it possible. \
The core idea is to dissect the spec file that describes the snapshot, organize its data and display it in a readable manner. \
This spec file can be provided by passing its path assuming it resides locally. But in the likely case it isn't, the script can download it for you, by being given an S3 URL and relevant parameters.

## Usage

The `locator_info.py` script expects only one argument for the path and many mostly optional parameters, most of which are for S3 connectivity and authentication.

### Help Message

```text
usage: locator_info.py [-h] [-v] [-j] [--download-path DOWNLOAD_PATH] [--access-key ACCESS_KEY] [--secret-key SECRET_KEY] [--endpoint-url ENDPOINT_URL] [--no-verify-ssl | --ca-bundle CA_BUNDLE] path

Parse stow spec info.
You may either provide a spec file path, or specify an S3 URL for the script to attemp and download one.
Credentials info in case an S3 URL is provided:
    - AWS S3: Either provide the `--access-key` and `--secret-key`, or have your machine/account configured according to https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
    - Other: Please consider using the `--access-key`, `--secret-key`, `--endpoint-url`, `--no-verify-ssl` and `--ca-bundle` options
        - If those options are not enough or something doesn't work quite right, please contact the weka support team. In the meanwhile, if possible you may download the file locally and provide its path to the script

positional arguments:
  path                  Path to a spec file or an S3 URL (s3://<bucket_name>/<locator>) pointing to one

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         More info
  -j, --json, -J        JSONifed data
  --download-path DOWNLOAD_PATH
                        In case an S3 URL path was provided, this path indicates where to download the spec file
  --access-key ACCESS_KEY, --access-key-id ACCESS_KEY
                        Optional access key, only relevant with S3 URL path
  --secret-key SECRET_KEY, --secret-access-key SECRET_KEY
                        Optional secret key, only relevant with S3 URL path
  --endpoint-url ENDPOINT_URL
                        Optional enpoint URL, only relevant with S3 URL path
  --no-verify-ssl       Optional flag to disable SSL verification, only relevant with S3 URL path
  --ca-bundle CA_BUNDLE
                        Optional custom CA certificate bundle to use when verifying SSL certificates, only relevant with S3 URL pathOptional custom CA certificate bundle to use when verifying SSL certificates, only relevant with S3 URL path
```

### Usage Examples

*Local spec file path:* `python3 locator_info.py /tmp/spec`

*AWS OBS:* `python3 locator_info.py s3://eu-west-1.weka.io.def-oo-test/aaaaaaaa/d/s/2/spec/aaaa-aaaa-aaaa-aaaaaaaaaaaa --download-path /tmp/spec --access-key MUCHRANDOM --secret-key MUCHRANDOMER`

*Other OBS with turned on TLS:* `python3 locator_info.py s3://test_bucket/aaaaaaaa/d/s/2/spec/aaaa-aaaa-aaaa-aaaaaaaaaaaa --download-path /tmp/spec --access-key YOUWISH --secret-key MUCHRANDOM --endpoint-url=https://hostname:9000 --no-verify-ssl`

### S3 Authentication and Connectivity

When being provided with an S3 URL the script attempts to access an object store to download the spec file. This operation is done by an external package called `boto3` which amongst many things handles connectivity, credentials and authentication. \
In its full form, the package is able to look for specific config files, environment variables, settings or properties to figure out all the options, more info can be found [here](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html). \
But in its simpler form, all options can be passed explicitly. The S3 parameters this script accepts are the one we thought might be useful, that includes basic access and secret keys, endpoint url and SSL options. We would recommend using the script's parameters when working against a local object store a non AWS remote one.

## Installation

The script requires python >=3.11. \
It also relies on external dependencies, to easily install them run `python3 -m pip install -r requirements.txt` \
NOTE: If `boto3` fails to download, you can still run the script but have to provide a path to a locally stored spec file and not an S3 URL.

## Things going wrong

As expected when dealing with object stores, downloads, parsing and display, many things can go wrong. The noteworthy ones are:

### Bad Data Warnings

Since the script is external, it might not always be up to date with how weka does things. Therefore, at any stage of its operation it might stumble into unrecognized data or format. \
But to not stop it from displaying what it can understand, instead of erroring it just issues a clear warning stating what's wrong and that the data may be partial and its integrity cannot be guaranteed. \
A simple example would be one of the snap layers having a version that is newer than the one the script supports.

### S3 Errors

Besides the obvious errors like bad arguments, non existing file path, invalid spec file etc. the script is able to recognize possible failing points in the process of S3 connection and authentication. This may include anything from a non existing bucket to SSL issues. \
When failing on one of those weak points, the script wraps the original error which might not always be clear and prefixes it with a short error summary. \
For example, if an authentication issue rises an error of the following format should be displayed: "Encountered an authentication issue, please verify your credentials. Original boto3 error: ...”

## Output Examples

*Regular output:*

```text
Number of snaplayers: 6
Uploader cluster GUID: e9fdda95-7f71-4067-92ba-d08b1885b280. With 1 other unique cluster GUIDs, use --verbose for more info
Compatible weka versions: v3.14.0+
Capacity: metadata: 2.5 MB, data: 629.1 MB, total: 631.6 MB
```

*Verbose mode & spec file contains a snap layer with an unsupported stow version*:

```text
WARN: Some of the objects' versioning is not supported by the script yet. Therefore some or all of the data might be partial and its integrity cannot be guaranteed
Number of snaplayers: 6

Snap layers:
  ID  GUID                                    No. Buckets  UTC Upload Date      Capacity: metadata    Capacity: data    Uploading Cluster Version
----  ------------------------------------  -------------  -------------------  --------------------  ----------------  -------------------------------------------------------------------------------------------
   0  97785401-e46b-4921-8648-d45d1ac3003c             80  2022-01-17 10:35:00  12.3 kB               4.1 kB            v3.13.0+
   2  97785401-e46b-4921-8648-d45d1ac3003c             80  2022-01-17 10:43:56  0 Bytes               0 Bytes           v3.13.0+
   6  97785401-e46b-4921-8648-d45d1ac3003c             80  2022-01-17 10:44:38  1.8 MB                471.9 MB          v3.13.0+
   9  97785401-e46b-4921-8648-d45d1ac3003c             80  2022-01-17 10:50:00  0 Bytes               0 Bytes           v3.13.0+
   5  e9fdda95-7f71-4067-92ba-d08b1885b280             80  2022-01-17 10:50:30  626.7 kB              157.3 MB          N/A (the script does not support this object's versioning, displayed data might be partial)
   8  e9fdda95-7f71-4067-92ba-d08b1885b280             80  2022-01-17 10:50:30  0 Bytes               0 Bytes           N/A (the script does not support this object's versioning, displayed data might be partial)

Unique GUIDs: {'e9fdda95-7f71-4067-92ba-d08b1885b280', '97785401-e46b-4921-8648-d45d1ac3003c'}
Compatible weka versions: N/A (the script does not support this object's versioning, displayed data might be partial)
Capacity: metadata: 2.5 MB, data: 629.1 MB, total: 631.6 MB
```

*Error example: Non existing spec file as path argument* \
`ERROR: The given path is not an existing file and not of the S3 URL syntax`

*Error example: Bad access key (showcases a boto3 error wrapping example)* \
`ERROR: Encountered an authentication issue, please verify your credentials. Original boto3 error: An error occurred (InvalidAccessKeyId) when calling the ListBuckets operation: The AWS Access Key Id you provided does not exist in our records.`
