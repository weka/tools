"""S3 logic helpers"""
from typing import Optional, Union

# DO NOT IMPORT boto3/botcore HERE:
#   those imports are purposefully nested inside the functions so boto dependency is needed only when we actually resort to downloading the spec file

from .common import CustomException, enforce


def download_spec_file(
    bucket_name: str,
    locator: str,
    download_path: str,
    verify_ssl: bool,
    access_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    endpoint_url: Optional[str] = None,
    ca_bundle: Optional[str] = None,
) -> None:
    import boto3
    from botocore.exceptions import ClientError

    s3 = boto3.client(
        "s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=endpoint_url,
        verify=_infer_verify_val(verify_ssl, ca_bundle),
    )

    all_buckets = _verify_s3_connection_and_get_buckets(s3)
    enforce(
        any(bucket["Name"] == bucket_name for bucket in all_buckets),
        f"Bucket {bucket_name} could not be found",
    )

    try:
        s3.download_file(bucket_name, locator, download_path)
    except ClientError as ex:
        raise CustomException(
            "Encountered an error while downloading the file, make sure the locator is valid and that it is associated with the provided bucket name."
            f" Original boto3 error: {ex}"
        ) from ex


def _infer_verify_val(verify_ssl: bool, ca_bundle: Optional[str]) -> Union[str, bool]:
    """boto3 client's `verify` param is of a bool/str type, expecting False if shouldn't verify SSL and a string if a CA bundle is provided"""
    if ca_bundle is not None:
        return ca_bundle
    return verify_ssl


def _verify_s3_connection_and_get_buckets(s3):
    from botocore.exceptions import ClientError, EndpointConnectionError, HTTPClientError, SSLError

    # the easiest way to verify credentials and connectivity is by trying to list buckets
    try:
        return s3.list_buckets()["Buckets"]
    except ClientError as ex:
        error_code = ex.response.get("Error", {}).get("Code", None)
        if error_code in ["SignatureDoesNotMatch", "InvalidAccessKeyId"]:
            raise CustomException(f"Encountered an authentication issue, please verify your credentials. Original boto3 error: {ex}") from ex
        raise ex
    except (EndpointConnectionError, HTTPClientError) as ex:
        raise CustomException(f"Encountered an issue with the enpoint url. Original boto3 error: {ex}") from ex
    except SSLError as ex:
        raise CustomException(f"Encountered an SSL issue. Original boto3 error: {ex}") from ex
