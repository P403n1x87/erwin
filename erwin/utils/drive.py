def to_file_map(file_list):
    return {file["id"]: file for file in file_list}




def diff(previous, current):
    prev_files = set(previous.keys())
    files = set(current.keys())

    new_files = [current[f] for f in files - prev_files]
    deleted_files = [previous[f] for f in prev_files - files]

    modified_files = {
        f for f in prev_files.intersection(files) if current[f] != previous[f]
    }

    renamed_files = []

    for f in modified_files:
        prev_file = previous[f]
        file = current[f]

        if prev_file["createdTime"] != file["createdTime"] or (
            prev_file["modifiedTime"] != file["modifiedTime"]
            and prev_file["md5Checksum"] != file["md5Checksum"]
        ):
            new_files.append(current[f])
            deleted_files.append(previous[f])
        elif get_paths(previous, prev_file) != get_paths(current, file):
            renamed_files.append((previous[f], current[f]))

    return new_files, renamed_files, deleted_files
