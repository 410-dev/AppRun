import argparse
import json
import os
import sys

def main():
    parser = argparse.ArgumentParser(description="Dictionary Utility")
    parser.add_argument("--dict-collection", required=True, help="Dictionary collection ID (Located in /usr/share/dictionaries)")
    parser.add_argument("--string", required=True, help="String value that contains text to substitute")
    args = parser.parse_args()

    # Iterate through all JSON files in the specified dictionary collection
    dict_collection_path = os.path.join("/usr/share/dictionaries", args.dict_collection)
    if not os.path.isdir(dict_collection_path):
        print(f"Error: Dictionary collection '{args.dict_collection}' does not exist.")
        return
    for filename in os.listdir(dict_collection_path):
        if filename.endswith(".json"):
            file_path = os.path.join(dict_collection_path, filename)
            with open(file_path, 'r') as file:
                try:
                    dictionary = json.load(file)
                    for key, value in dictionary.items():
                        args.string = args.string.replace(key, value)
                except json.JSONDecodeError:
                    print(f"Error: Failed to parse JSON file '{filename}'. Skipping.")
    print(args.string)
    return 0


if __name__ == "__main__":
    sys.exit(main())
