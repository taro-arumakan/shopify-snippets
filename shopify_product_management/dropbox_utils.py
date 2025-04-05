import os
import requests
import zipfile

def download_images_from_dropbox(shared_link, output_path):

    shared_link = shared_link.replace('&dl=0', '') + '&dl=1'
    res = requests.get(shared_link)
    with open(f'{output_path}.zip', 'wb') as of:
        of.write(res.content)
    if not os.path.exists(output_path):
        os.mkdir(output_path)
    with zipfile.ZipFile(f'{output_path}.zip') as zipref:
        zipref.extractall(output_path)
    os.remove(f'{output_path}.zip')

def rename_files(srcdir, destdir, prefix):
    res = []
    for i, fname in enumerate(sorted(os.listdir(srcdir))):
        target = f'{destdir}/{prefix}_{str(i).zfill(2)}_{fname}'
        os.rename(f'{srcdir}/{fname}', target)
        res.append(target)
    return res

def download_and_rename_images_from_dropbox(output_path, images_link, prefix, tempdir='tmp'):
    if not os.path.exists(output_path):
        os.mkdir(output_path)
    download_images_from_dropbox(images_link, tempdir)
    return rename_files(tempdir, output_path, prefix)


def download_files(product_name, main_images_link, detail_images_link, sku_imageslink_map, tempdir='tmp'):
    if not os.path.exists(product_name):
        os.mkdir(product_name)
    download_images_from_dropbox(main_images_link, tempdir)
    rename_files(tempdir, product_name, 'product_main')

    download_images_from_dropbox(detail_images_link, tempdir)
    rename_files(tempdir, product_name, 'product_details')

    for sku, link in sku_imageslink_map.items():
        download_images_from_dropbox(link, tempdir)
        rename_files(tempdir, product_name, sku)
