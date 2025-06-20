"""Argument parsing utils and helpers"""

import argparse
from typing import Optional
from os.path import isfile

from .common import CustomException, enforce
from .s3 import download_spec_file

HELP_DESCRIPTION = """
Parse stow spec info.
You may either provide a spec file path, or specify an S3 URL for the script to attemp and download one.
Credentials info in case an S3 URL is provided:
    - AWS S3: Either provide the `--access-key` and `--secret-key`, or have your machine/account configured according to https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html
    - Other: Please consider using the `--access-key`, `--secret-key`, `--endpoint-url`, `--no-verify-ssl` and `--ca-bundle` options
        - If those options are not enough or something doesn't work quite right, please contact the weka support team. In the meanwhile, if possible you may download the file locally and provide its path to the script
"""


def parse_args():
    arg_parser = argparse.ArgumentParser(description=HELP_DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter)
    arg_parser.add_argument(
        "path",
        type=str,
        help="Path to a spec file or an S3 URL (s3://<bucket_name>/<locator>) pointing to one",
    )
    arg_parser.add_argument("-v", "--verbose", action="store_true", help="More info")
    arg_parser.add_argument("-j", "--json", "-J", action="store_true", help="JSONifed data")
    arg_parser.add_argument("--raw", action="store_true", help=argparse.SUPPRESS)
    arg_parser.add_argument("--verbose-errors", action="store_true", help=argparse.SUPPRESS)
    arg_parser.add_argument(
        "--download-path",
        type=str,
        default=None,
        help="In case an S3 URL path was provided, this path indicates where to download the spec file",
    )
    arg_parser.add_argument(
        "--access-key",
        "--access-key-id",
        type=str,
        default=None,
        help="Optional access key, only relevant with S3 URL path",
    )
    arg_parser.add_argument(
        "--secret-key",
        "--secret-access-key",
        type=str,
        default=None,
        help="Optional secret key, only relevant with S3 URL path",
    )
    arg_parser.add_argument(
        "--endpoint-url",
        type=str,
        default=None,
        help="Optional enpoint URL, only relevant with S3 URL path",
    )
    ssl_group = arg_parser.add_mutually_exclusive_group()
    ssl_group.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Optional flag to disable SSL verification, only relevant with S3 URL path",
    )
    ssl_group.add_argument(
        "--ca-bundle",
        type=str,
        default=None,
        help="Optional custom CA certificate bundle to use when verifying SSL certificates, only relevant with S3 URL path",
    )
    return arg_parser.parse_args()


def parse_path_arg(
    path_arg: str,
    verify_ssl: bool,
    spec_file_download_path: str | None = None,
    access_key: str | None = None,
    secret_key: str | None = None,
    endpoint_url: str | None = None,
    ca_bundle: str | None = None,
) -> str:
    """Infer if path arg represents a file path or an S3 URL. If URL, download the spec file to the given download path. Regardless, return the spec file path"""
    url_indicator = "s3://"
    if path_arg.startswith(url_indicator):
        if spec_file_download_path is None:
            raise CustomException("Download path for spec file is required if path argument is an S3 URL")

        bucket_name, locator = path_arg[len(url_indicator) :].split("/", 1)
        download_spec_file(
            bucket_name,
            locator,
            spec_file_download_path,
            access_key=access_key,
            secret_key=secret_key,
            endpoint_url=endpoint_url,
            verify_ssl=verify_ssl,
            ca_bundle=ca_bundle,
        )
        return spec_file_download_path

    enforce(
        spec_file_download_path is None,
        "Path to download the spec file to should only be provided if the path argument is an S3 URL",
    )
    enforce(
        isfile(path_arg),
        "The given path is not an existing file and not of the S3 URL syntax",
    )
    return path_arg
