#!/usr/bin/env python3

import requests
import os
import argparse
import json

# --- Channel ID Constants ---
HPC_CHANNEL = "C03AWLD6UG3"
S3_CHANNEL = "C02KX3GN0LT"

def upload_file_to_slack(file_path, channel_id, initial_comment, slack_token):
    """
    Uploads a file to Slack using the 3-step external upload API.
    """

    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    file_name = os.path.basename(file_path)

    # --- Step 1: Request upload URL ---
    print("Step 1: Requesting upload URL...")
    url_get_upload = "https://slack.com/api/files.getUploadURLExternal"
    headers_auth = {"Authorization": f"Bearer {slack_token}"}
    # Get file size
    file_size = os.path.getsize(file_path)
    data_get_upload = {
        "filename": file_name,
        "length": file_size
    }

    try:
        # Use data= instead of json= for this specific endpoint
        response_get_upload = requests.post(
            url_get_upload,
            headers=headers_auth,
            data=data_get_upload
        )
        response_get_upload.raise_for_status()  # Check for HTTP errors
        upload_data = response_get_upload.json()

        if not upload_data.get("ok"):
            print(f"Error getting upload URL: {upload_data.get('error', 'Unknown error')}")
            # Print more details if available
            if 'args' in upload_data:
                 print(f"Debug Info (args): {upload_data['args']}")
            return

        upload_url = upload_data["upload_url"]
        file_id = upload_data["file_id"]

        print(f"Upload URL: {upload_url}")
        print(f"File ID: {file_id}")

    except requests.exceptions.RequestException as e:
        print(f"HTTP Error during step 1: {e}")
        return
    except KeyError:
        print("Error: 'upload_url' or 'file_id' not found in Slack response.")
        print(f"Response: {upload_data}")
        return

    # --- Step 2: Upload file binary ---
    print("\nStep 2: Uploading file binary...")
    try:
        with open(file_path, "rb") as file_content:
            # Ensure Content-Length is provided — some upload endpoints require it
            headers_put = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(file_size)
            }
            # Use a reasonable timeout so the script doesn't hang indefinitely
            response_upload = requests.put(
                upload_url,
                headers=headers_put,
                data=file_content,
                timeout=120
            )

            # Print status + short response body for debugging (truncated)
            print(f"Upload response status: {response_upload.status_code}")
            text_preview = (response_upload.text or "")[:1000]
            if text_preview:
                print(f"Upload response body (truncated): {text_preview}")

            response_upload.raise_for_status()

        print("File binary uploaded successfully.")

    except requests.exceptions.RequestException as e:
        # Separate out timeouts for clarity
        if isinstance(e, requests.exceptions.Timeout):
            print(f"HTTP Timeout during step 2: {e}")
        else:
            print(f"HTTP Error during step 2: {e}")
        return
    except IOError as e:
        print(f"File read error: {e}")
        return

    # --- Step 3: Complete upload ---
    print("\nStep 3: Completing file upload...")
    url_complete_upload = "https://slack.com/api/files.completeUploadExternal"

    # This step *DOES* use JSON, so this is correct.
    # channel_ids must be an array of channel IDs according to the API.
    data_complete_upload = {
        "files": [
            {
                "id": file_id,
                "title": file_name
            }
        ],
        "initial_comment": initial_comment,
        "channel_ids": [channel_id] if channel_id else []
    }

    try:
        response_complete = requests.post(
            url_complete_upload,
            headers=headers_auth,
            json=data_complete_upload
        )
        response_complete.raise_for_status()

        complete_data = response_complete.json()

        if complete_data.get("ok"):
            print("File upload successfully completed!")

            # Diagnostic: fetch file info to verify which channels it's shared to
            try:
                resp_info = requests.get(
                    "https://slack.com/api/files.info",
                    headers=headers_auth,
                    params={"file": file_id},
                    timeout=30
                )
                resp_info.raise_for_status()
                info_data = resp_info.json()
                print("files.info response:", json.dumps(info_data, indent=2)[:2000])

                # If the file is not shared to the desired channel, post a message with the file permalink
                file_obj = info_data.get("file", {})
                # Check shares or channels fields (may differ by response)
                shared_to = []
                if "channels" in file_obj:
                    shared_to = file_obj.get("channels") or []
                elif "shares" in file_obj:
                    # shares is a dict keyed by channel/team — collect channel ids
                    for team_id, share_map in file_obj["shares"].items():
                        for ch, arr in share_map.items():
                            shared_to.append(ch)

                if channel_id and channel_id not in shared_to:
                    # Attempt to post a message linking to the file so it appears in the channel
                    permalink = file_obj.get("permalink") or file_obj.get("url_private")
                    if permalink:
                        post_payload = {
                            "channel": channel_id,
                            "text": f"{initial_comment or ''} {permalink}"
                        }
                        resp_post = requests.post(
                            "https://slack.com/api/chat.postMessage",
                            headers=headers_auth,
                            json=post_payload,
                            timeout=30
                        )
                        try:
                            resp_post.raise_for_status()
                        except requests.exceptions.RequestException:
                            print("chat.postMessage failed:", resp_post.text[:1000])
                        else:
                            post_data = resp_post.json()
                            if post_data.get("ok"):
                                print("Posted message linking file to channel (via chat.postMessage)")
                            else:
                                print("chat.postMessage returned error:", post_data.get("error"))
                    else:
                        print("No permalink available to share the file into the channel automatically.")

            except requests.exceptions.RequestException as e:
                print(f"files.info/chat.postMessage diagnostic error: {e}")
        else:
            print(f"Error completing upload: {complete_data.get('error', 'Unknown error')}")
            print(f"Response: {complete_data}")

    except requests.exceptions.RequestException as e:
        print(f"HTTP Error during step 3: {e}")
        return

def main():
    parser = argparse.ArgumentParser(description="Upload a file to a Slack channel.")

    parser.add_argument(
        "-f", "--file",
        help="Path to the file to upload.",
        required=True
    )
    parser.add_argument(
        "-m", "--comment",
        help="Initial comment to post with the file.",
        default="File upload"
    )

    # Token can be provided as a flag or from an environment variable
    default_token = os.environ.get("SLACK_TOKEN")
    parser.add_argument(
        "-t", "--token",
        help="Slack API token (or set SLACK_TOKEN env var).",
        default=default_token,
        required=default_token is None  # Required only if env var is not set
    )

    # --- UPDATED SECTION ---
    # Add a mutually exclusive group for channel selection
    # The user MUST provide one of these options.
    channel_group = parser.add_mutually_exclusive_group(required=True)

    channel_group.add_argument(
        "--hpc",
        help=f"Upload to the HPC channel ({HPC_CHANNEL})",
        action="store_true"  # This makes it a boolean flag
    )
    channel_group.add_argument(
        "--s3",
        help=f"Upload to the S3 channel ({S3_CHANNEL})",
        action="store_true"
    )
    channel_group.add_argument(
        "-c", "--channel",
        help="Specify a custom channel ID."
    )
    # --- END UPDATED SECTION ---

    args = parser.parse_args()

    # Determine which channel ID to use based on the flags
    channel_id = ""
    if args.hpc:
        channel_id = HPC_CHANNEL
    elif args.s3:
        channel_id = S3_CHANNEL
    elif args.channel:
        channel_id = args.channel

    upload_file_to_slack(args.file, channel_id, args.comment, args.token)

if __name__ == "__main__":
    main()
