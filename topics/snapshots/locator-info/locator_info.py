"""
Parse stow spec info.
"""

import sys

from src.common import CustomException, RawDataContainerType
from src.args import parse_args, parse_path_arg
from src.output import display_data
from src.spec_file import SpecFile

verbose_errors = False


def main():
    args = parse_args()

    global verbose_errors
    verbose_errors = args.verbose_errors

    spec_file_path = parse_path_arg(
        path_arg=args.path,
        spec_file_download_path=args.download_path,
        access_key=args.access_key,
        secret_key=args.secret_key,
        endpoint_url=args.endpoint_url,
        verify_ssl=not args.no_verify_ssl,
        ca_bundle=args.ca_bundle,
    )

    raw_data: RawDataContainerType = SpecFile(spec_file_path).deserialize()

    if args.raw:  # for internal debugging use
        print(raw_data)
    else:
        display_data(raw_data, verbose=args.verbose, json=args.json)


if __name__ == "__main__":
    try:
        main()
    except CustomException as error:
        if verbose_errors:
            raise error
        sys.exit(error)
