import hashlib

def hash_file(filename, hash_type="sha256"):
    """returns a checksum of the specified file"""
    progress = 0
    file_hash = hashlib.new(hash_type)
    with open(filename, "rb") as file:
        for block in iter(lambda: file.read(4096), b""):
            file_hash.update(block)
            progress += len(block)
            # progress bar here
        return file_hash.hexdigest()


def is_valid_download(filename, checksum):
    file_hash = hash_file(filename)
    return file_hash == checksum
