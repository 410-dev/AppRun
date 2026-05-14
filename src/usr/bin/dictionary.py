import argparse
import json
import sys
from pathlib import Path

DICTIONARY_ROOT = Path("/usr/share/dictionaries")

def main():
    parser = argparse.ArgumentParser(description="Dictionary Utility")
    parser.add_argument("--dict-collection", required=True, help="Dictionary collection ID (Located in /usr/share/dictionaries)")
    parser.add_argument("--string", required=True, help="String value that contains text to substitute")
    args = parser.parse_args()

    # Iterate through all JSON files in the specified dictionary collection
    dict_collection_path = (DICTIONARY_ROOT / args.dict_collection).resolve()
    root = DICTIONARY_ROOT.resolve()
    if dict_collection_path != root and root not in dict_collection_path.parents:
        print(f"Error: Dictionary collection '{args.dict_collection}' is outside the dictionary root.")
        return 1
    if not dict_collection_path.is_dir():
        print(f"Error: Dictionary collection '{args.dict_collection}' does not exist.")
        return 1
    for file_path in dict_collection_path.iterdir():
        if file_path.name.endswith(".json") and file_path.is_file():
            with open(file_path, 'r') as file:
                try:
                    dictionary = json.load(file)
                    for key, value in dictionary.items():
                        args.string = args.string.replace(key, value)
                except json.JSONDecodeError:
                    print(f"Error: Failed to parse JSON file '{file_path.name}'. Skipping.")
    print(args.string)
    return 0


if __name__ == "__main__":
    sys.exit(main())
