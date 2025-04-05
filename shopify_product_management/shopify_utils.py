import json
import logging
import requests
import time

logger = logging.getLogger(__name__)
stream_handler = logging.StreamHandler()
logger.addHandler(stream_handler)
logger.setLevel(logging.INFO)

def _remove_unrelated_medias(shop_name, access_token, new_product_id, variant_ids_to_keep):
    all_medias = medias_by_product_id(shop_name, access_token, new_product_id)
    keep_medias = medias_by_variant_id(shop_name, access_token, variant_ids_to_keep[0])
    media_ids_to_remove = [m['id'] for m in all_medias if m['id'] not in [km['id'] for km in keep_medias]]
    remove_product_media_by_product_id(shop_name, access_token, new_product_id, media_ids_to_remove)

def product_variants_to_products(shop_name, access_token, product_title, new_status='DRAFT'):
    product = product_by_title(shop_name, access_token, product_title)
    product_id = product['id']
    product_handle = product['handle']
    variants = product_variants_by_product_id(shop_name, access_token, product_id)
    color_options = set([so['value'] for v in variants for so in v['selectedOptions'] if so['name'] == 'カラー'])

    new_product_ids = []
    for color_option in color_options:
        res = duplicate_product(shop_name, access_token, product_id, product_title, True, new_status)
        new_product = res['productDuplicate']['newProduct']
        new_product_id = new_product['id']
        logger.info(f"Duplicated product ID: {new_product_id}")
        new_product_ids.append(new_product_id)
        new_product_handle = '-'.join([product_handle, '-'.join(color_option.lower().split(' '))])
        color_option_id = [o['id'] for o in new_product['options'] if o['name']=='カラー']
        assert len(color_option_id) == 1, f"{'Multiple' if color_option_id else 'No'} option カラー for {new_product_id}"
        color_option_id = color_option_id[0]
        new_variants = new_product['variants']['nodes']
        variant_ids_to_keep = [v['id'] for v in new_variants if any(so['name']=='カラー' and so['value']==color_option for so in v['selectedOptions'])]
        variant_ids_to_remove = [v['id'] for v in new_variants if v['id'] not in variant_ids_to_keep]

        _remove_unrelated_medias(shop_name, access_token, new_product_id, variant_ids_to_keep)
        remove_product_variants(shop_name, access_token, new_product_id, variant_ids_to_remove)
        delete_product_options(shop_name, access_token, new_product_id, [color_option_id])
        update_product_handle(shop_name, access_token, new_product_id, new_product_handle)
        update_variation_value_metafield(shop_name, access_token, new_product_id, color_option)

    for new_product_id in new_product_ids:
        update_variation_products_metafield(shop_name, access_token, new_product_id, new_product_ids)

def duplicate_product(shop_name, access_token, product_id, new_title, include_images=False, new_status='DRAFT'):
    query = """
    mutation DuplicateProduct($productId: ID!, $newTitle: String!, $includeImages: Boolean, $newStatus: ProductStatus) {
        productDuplicate(productId: $productId, newTitle: $newTitle, includeImages: $includeImages, newStatus: $newStatus) {
            newProduct {
                id
                handle
                title
                vendor
                productType
                variants(first: 10) {
                    nodes {
                        id
                        title
                        selectedOptions {
                            name
                            value
                        }
                    }
                }
                options {
                    id
                    name
                    values
                }
            }
            imageJob {
                id
                done
            }
            userErrors {
                field
                message
            }
        }
    }
    """
    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
        'productId': product_id,
        'newTitle': new_title,
        'includeImages': include_images,
        'newStatus': new_status
    }
    res = run_query(shop_name, access_token, query, variables)
    if res['productDuplicate']['userErrors']:
        raise RuntimeError(f"Failed to duplicate the product: {res['productDuplicate']['userErrors']}")
    return res

def remove_product_variants(shop_name, access_token, product_id, variant_ids):
    query = """
    mutation bulkDeleteProductVariants($productId: ID!, $variantsIds: [ID!]!) {
        productVariantsBulkDelete(productId: $productId, variantsIds: $variantsIds) {
            product {
                id
                title
            }
            userErrors {
                field
                message
            }
        }
    }
    """
    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
        "productId": product_id,
        "variantsIds": variant_ids
    }
    res = run_query(shop_name, access_token, query, variables)
    if res['productVariantsBulkDelete']['userErrors']:
        raise RuntimeError(f"Failed to update the tags: {res['productSet']['userErrors']}")
    return res

def delete_product_options(shop_name, access_token, product_id, option_ids):
    query = """
    mutation deleteOptions($productId: ID!, $options: [ID!]!) {
    productOptionsDelete(productId: $productId, options: $options, strategy: DEFAULT) {
        userErrors {
            field
            message
            code
        }
        deletedOptionsIds
        product {
            id
            options {
                id
                name
                values
                position
                optionValues {
                id
                name
                hasVariants
                }
            }
        }
    }
    }
    """
    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
        "productId": product_id,
        "options": option_ids
    }
    res = run_query(shop_name, access_token, query, variables)
    if res['productOptionsDelete']['userErrors']:
        raise RuntimeError(f"Failed to update the tags: {res['productOptionsDelete']['userErrors']}")
    return res

def update_product_attribute(shop_name, access_token, product_id, attribute_name, attribute_value):
    query = """
    mutation productSet($productSet: ProductSetInput!) {
        productSet(synchronous:true, input: $productSet) {
          product {
            id
            %s
          }
          userErrors {
            field
            code
            message
          }
        }
    }
    """ % attribute_name
    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
      "productSet": {
        "id": product_id,
        attribute_name: attribute_value
      }
    }
    res = run_query(shop_name, access_token, query, variables)
    if res['productSet']['userErrors']:
        raise RuntimeError(f"Failed to update {attribute_name}: {res['productSet']['userErrors']}")
    return res

def update_product_tags(shop_name, access_token, product_id, tags):
    return update_product_attribute(shop_name, access_token, product_id, 'tags', tags)

def update_product_description(shop_name, access_token, product_id, desc):
    return update_product_attribute(shop_name, access_token, product_id, 'descriptionHtml', desc)

def update_product_handle(shop_name, access_token, product_id, handle):
    return update_product_attribute(shop_name, access_token, product_id, 'handle', handle)


def sanitize_image_name(image_name):
    return image_name.replace(' ', '_').replace('[', '').replace(']', '_').replace('(', '').replace(')', '')

def image_htmlfragment_in_description(image_name, sequence, shopify_url_prefix):
    animation_classes = ['reveal_tran_bt', 'reveal_tran_rl', 'reveal_tran_lr', 'reveal_tran_tb']
    animation_class = animation_classes[sequence % 4]
    return f'<p class="{animation_class}"><img src="{shopify_url_prefix}/files/{sanitize_image_name(image_name)}" alt=""></p>'


def upload_and_assign_description_images_to_shopify(shop_name, access_token, product_id, local_paths, dummy_product_id, shopify_url_prefix):
    local_paths = [local_path for local_path in local_paths if not local_path.endswith('.psd')]
    mime_types = [f'image/{local_path.rsplit('.', 1)[-1].lower()}' for local_path in local_paths]
    staged_targets = generate_staged_upload_targets(shop_name, access_token, local_paths, mime_types)
    logger.info(f'generated staged upload targets: {len(staged_targets)}')
    upload_images_to_shopify(staged_targets, local_paths, mime_types)
    description = '\n'.join(image_htmlfragment_in_description(local_path.rsplit('/', 1)[-1], i, shopify_url_prefix) for i, local_path in enumerate(local_paths))
    assign_images_to_product(shop_name, access_token,
                             [target['resourceUrl'] for target in staged_targets],
                             alts=[local_path.rsplit('/', 1)[-1] for local_path in local_paths],
                             product_id=dummy_product_id)
    return update_product_description(shop_name, access_token, product_id, description)

def file_id_by_file_name(shop_name, access_token, file_name):
    query = '''

      query {
        files(first:10 query:"filename:'%s'") {
          nodes {
            id
            ... on MediaImage {
              image {
                url
              }
            }
          }
        }
      }
      ''' % file_name.rsplit('.', 1)[0]
    res = run_query(shop_name, access_token, query)
    res = res['files']['nodes']
    if len(res) > 1:
        res = [r for r in res if r['image']['url'].rsplit('?', 1)[0].endswith(file_name)]
    assert len(res) == 1, f'{"Multiple" if res else "No"} files found for {file_name}: {res}'
    return res[0]['id']


def _replace_image_files_with_staging(shop_name, access_token, staged_targets, local_paths, mime_types):
    filenames = [sanitize_image_name(path.rsplit('/', 1)[-1]) for path in local_paths]
    file_ids = [file_id_by_file_name(shop_name, access_token, filename) for filename in filenames]
    resource_urls = [target['resourceUrl'] for target in staged_targets]
    query = """
      mutation FileUpdate($input: [FileUpdateInput!]!) {
        fileUpdate(files: $input) {
          userErrors {
            code
            field
            message
          }
          files {
            alt
          }
        }
      }
      """
    medias = [{
        "id": file_id,
        "originalSource": url,
        "alt": filename
    } for file_id, url, filename in zip(file_ids, resource_urls, filenames)]

    variables = {
        "input": medias
    }
    res = run_query(shop_name, access_token, query, variables)
    if res['fileUpdate']['userErrors']:
        raise RuntimeError(f"Failed to update the files: {res['fileUpdate']['userErrors']}")
    return res['fileUpdate']

def replace_image_files(shop_name, access_token, local_paths):
    mime_types = [f'image/{local_path.rsplit('.', 1)[-1].lower()}' for local_path in local_paths]
    staged_targets = generate_staged_upload_targets(shop_name, access_token, local_paths, mime_types)
    logger.info(f'generated staged upload targets: {len(staged_targets)}')
    upload_images_to_shopify(staged_targets, local_paths, mime_types)
    return _replace_image_files_with_staging(shop_name, access_token, staged_targets, local_paths, mime_types)


def update_product_metafield(shop_name, access_token, product_id, metafield_namespace, metafield_key, value):
    query = """
    mutation updateProductMetafield($input: ProductInput!) {
        productUpdate(input: $input) {
          product {
            id
            metafields (first:10) {
              nodes {
                id
                namespace
                key
                value
              }
            }
          }
          userErrors {
            field
            message
          }
        }
    }
    """

    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
      "input": {
        "id": product_id,
        "metafields": [
          {
            "namespace": metafield_namespace,
            "key": metafield_key,
            "value": value
          }
        ]
      }
    }
    res = run_query(shop_name, access_token, query, variables)
    if user_errors := res['productUpdate']['userErrors']:
        raise RuntimeError(f"Failed to update the metafield: {user_errors}")
    return res


def update_variation_value_metafield(shop_name, access_token, product_id, variation_value):
    return update_product_metafield(shop_name, access_token, product_id, 'custom', 'variation_value', variation_value)

def update_variation_products_metafield(shop_name, access_token, product_id, variation_product_ids):
    return update_product_metafield(shop_name, access_token, product_id, 'custom', 'variation_products', json.dumps(variation_product_ids))

def update_product_description_metafield(shop_name, access_token, product_id, desc):
    return update_product_metafield(shop_name, access_token, product_id, 'custom', 'product_description', json.dumps(desc))

def update_size_table_html_metafield(shop_name, access_token, product_id, html_text):
    return update_product_metafield(shop_name, access_token, product_id, 'custom', 'size_table_html', html_text)

def metafield_id_by_namespace_and_key(shop_name, access_token, namespace, key, owner_type='PRODUCT'):
    query = '''
      query {
        metafieldDefinitions(first:10, ownerType:%s, namespace:"%s", key:"%s") {
          nodes {
            id
          }
        }
      }
    ''' % (owner_type, namespace, key)
    res = run_query(shop_name, access_token, query)
    res = res['metafieldDefinitions']['nodes']
    assert len(res) == 1, f'{"Multiple" if res else "No"} metafields found for {namespace}:{key}: {res}'
    return res[0]['id']

def update_product_description_and_size_table_html_metafields(shop_name, access_token, product_id, desc, html_text):
    query = """
    mutation updateProductMetafield($productSet: ProductSetInput!) {
        productSet(synchronous:true, input: $productSet) {
          product {
            id
            metafields (first:10) {
              nodes {
                id
                namespace
                key
                value
              }
            }
          }
          userErrors {
            field
            code
            message
          }
        }
    }
    """

    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    product_description_mf_id = metafield_id_by_namespace_and_key(shop_name, access_token, 'custom', 'product_description')
    size_table_html_mf_id = metafield_id_by_namespace_and_key(shop_name, access_token, 'custom', 'size_table_html')
    variables = {
      "productSet": {
        "id": product_id,
        "metafields": [
          {
            "id": product_description_mf_id,
            "namespace": "custom",
            "key": "product_description",
            "type": "rich_text_field",
            "value": json.dumps(desc)
          },
          {
            "id": size_table_html_mf_id,
            "namespace": "custom",
            "key": "size_table_html",
            "type": "multi_line_text_field",
            "value": html_text
          }
        ]
      }
    }

    res = run_query(shop_name, access_token, query, variables)
    if res['productSet']['userErrors']:
        raise RuntimeError(f"Failed to update the metafield: {res['productSet']['userErrors']}")
    return res


# TODO: metafield id by namespace and key
def old_update_product_description_metafield(shop_name, access_token, product_id, desc):
    query = """
    mutation updateProductMetafield($productSet: ProductSetInput!) {
        productSet(synchronous:true, input: $productSet) {
          product {
            id
            metafields (first:10) {
              nodes {
                id
                namespace
                key
                value
              }
            }
          }
          userErrors {
            field
            code
            message
          }
        }
    }
    """

    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
      "productSet": {
        "id": product_id,
        "metafields": [
          {
            "id": "gid://shopify/Metafield/37315032023281",
            "namespace": "custom",
            "key": "product_description",
            "type": "rich_text_field",
            "value": json.dumps(desc)
          }
        ]
      }
    }

    res = run_query(shop_name, access_token, query, variables)
    if res['productSet']['userErrors']:
        raise RuntimeError(f"Failed to update the metafield: {res['productSet']['userErrors']}")
    return res


# TODO: metafield id by namespace and key
def old_update_size_table_html_metafield(shop_name, access_token, product_id, html_text):
    query = """
    mutation updateProductMetafield($productSet: ProductSetInput!) {
        productSet(synchronous:true, input: $productSet) {
          product {
            id
            metafields (first:10) {
              nodes {
                id
                namespace
                key
                value
              }
            }
          }
          userErrors {
            field
            code
            message
          }
        }
    }
    """

    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {
      "productSet": {
        "id": product_id,
        "metafields": [
          {
            "id": "gid://shopify/Metafield/30082966716672",
            "namespace": "custom",
            "key": "size_table_html",
            "type": "multi_line_text_field",
            "value": html_text
          }
        ]
      }
    }

    res = run_query(shop_name, access_token, query, variables)
    if res['productSet']['userErrors']:
        raise RuntimeError(f"Failed to update the metafield: {res['productSet']['userErrors']}")
    return res


def product_description_by_product_id(shop_name, access_token, product_id):
    if isinstance(product_id, int) or product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    query = '''
      query {
        product(id: "%s") {
          id
          descriptionHtml
        }
      }
    ''' % product_id
    res = run_query(shop_name, access_token, query)
    return res['product']['descriptionHtml']


def set_product_description_metafield(shop_name, access_token, product_id, description_rich_text):
    query = '''
    mutation MetafieldsSet($metafields: [MetafieldsSetInput!]!) {
    metafieldsSet(metafields: $metafields) {
        metafields {
        key
        namespace
        value
        }
        userErrors {
        field
        message
        code
        }
    }
    }
    '''

    import json
    description_rich_text = json.dumps(description_rich_text)

    variables = {
        "metafields": [
            {
                "key": "product_description",
                "namespace": "custom",
                "ownerId": f"gid://shopify/Product/{product_id}",
                "value": description_rich_text
            }
        ]
    }
    return run_query(shop_name, access_token, query, variables)


def product_by_query(shop_name, access_token, query_string):
    query = """
    query productsByQuery($query_string: String!) {
        products(first: 10, query: $query_string, sortKey: TITLE) {
            nodes {
                id
                title
                handle
                metafields (first:10) {
                    nodes {
                        id
                        namespace
                        key
                        value
                    }
                }
            }
        }
    }
    """
    variables = {
        "query_string": query_string
    }
    res = run_query(shop_name, access_token, query, variables)
    products = res['products']['nodes']
    if len(products) != 1:
        raise Exception(f"{'Multiple' if products else 'No'} products found for {query_string}: {products}")
    return products[0]

def product_by_title(shop_name, access_token, title):
    return product_by_query(shop_name, access_token, f"title:'{title}'")

def product_id_by_title(shop_name, access_token, title):
    return product_by_title(shop_name, access_token, title)['id']

def product_by_handle(shop_name, access_token, handle):
    return product_by_query(shop_name, access_token, f"handle:'{handle}'")

def product_id_by_handle(shop_name, access_token, handle):
    return product_by_handle(shop_name, access_token, handle)['id']


def medias_by_product_id(shop_name, access_token, product_id):
    query = """
    query ProductMediaStatusByID($productId: ID!) {
      product(id: $productId) {
        media(first: 100) {
          nodes {
            id
            alt
            ... on MediaImage {
            	image{
                url
              }
            }
            mediaContentType
            status
            mediaErrors {
              code
              details
              message
            }
            mediaWarnings {
              code
              message
            }
          }
        }
      }
    }
    """
    if product_id.isnumeric():
        product_id = f'gid://shopify/Product/{product_id}'
    variables = {"productId": product_id}
    res = run_query(shop_name, access_token, query, variables)
    return res['product']['media']['nodes']


def product_variants_by_product_id(shop_name, access_token, product_id):
    if product_id.startswith('gid://'):
        assert '/Product/' in product_id, f'non-product gid was provided: {product_id}'
        product_id = product_id.rsplit('/', 1)[-1]
    query = """
      {
        productVariants(first:10, query: "product_id:%s") {
          nodes {
            id
            title
            displayName
            sku
            media (first:50){
              nodes{
                id
                ... on MediaImage {
                  image{
                    url
                  }
                }
              }
            }
            selectedOptions {
                name
                value
            }
          }
        }
      }
    """ % product_id
    res = run_query(shop_name, access_token, query)
    return res['productVariants']['nodes']


def product_id_by_variant_id(shop_name, access_token, variant_id):
    if variant_id.isnumeric():
        variant_id = f'gid://shopify/ProductVariant/{variant_id}'
    query = """
      {
        productVariant(id:"%s") {
          displayName,
          product{
            title
            id
          }
        }
      }
    """ % variant_id
    res = run_query(shop_name, access_token, query)
    return res['productVariant']['product']['id']


def remove_product_media_by_product_id(shop_name, access_token, product_id, media_ids=None):
    if not media_ids:
      media_nodes = medias_by_product_id(shop_name, access_token, product_id)
      media_ids = [node['id'] for node in media_nodes]

    if not media_ids:
        logger.debug(f"Nothing to delete for {product_id}")
        return True

    logger.info(f"Going to delete {media_ids} from {product_id}")

    query = """
    mutation deleteProductMedia($productId: ID!, $mediaIds: [ID!]!) {
      productDeleteMedia(productId: $productId, mediaIds: $mediaIds) {
        deletedMediaIds
        product {
          id
        }
        mediaUserErrors {
          code
          field
          message
        }
      }
    }
    """

    variables = {
        "productId": product_id,
        "mediaIds": media_ids
    }
    res = run_query(shop_name, access_token, query, variables)
    logger.info(f'Initial media status for deletion:\n{res}')
    status = wait_for_media_processing_completion(shop_name, access_token, product_id)
    if not status:
        raise Exception("Error during media processing")


def assign_images_to_product(shop_name, access_token, resource_urls, alts, product_id):
    mutation_query = """
    mutation productCreateMedia($media: [CreateMediaInput!]!, $productId: ID!) {
      productCreateMedia(media: $media, productId: $productId) {
        media {
          alt
          mediaContentType
          status
        }
        userErrors {
          field
          message
        }
        product {
          id
          title
        }
      }
    }
    """

    medias = [{
        "originalSource": url,
        "alt": alt,
        "mediaContentType": "IMAGE"
    } for url, alt in zip(resource_urls, alts)]

    variables = {
        "media": medias,
        "productId": product_id
    }

    res = run_query(shop_name, access_token, mutation_query, variables)

    logger.debug("Initial media status:")
    logger.debug(res)

    if res['productCreateMedia']['userErrors']:
        raise RuntimeError(f"Failed to assign images to product: {res['productCreateMedia']['userErrors']}")

    status = wait_for_media_processing_completion(shop_name, access_token, product_id)
    if not status:
        raise Exception("Error during media processing")


def wait_for_media_processing_completion(shop_name, access_token, product_id, timeout_minutes=10):
    poll_interval = 5  # Poll every 5 seconds
    max_attempts = int((timeout_minutes * 60) / poll_interval)
    attempts = 0

    while attempts < max_attempts:
        media_nodes = medias_by_product_id(shop_name, access_token, product_id)
        processing_items = [
            node for node in media_nodes if node['status'] == "PROCESSING"]
        failed_items = [
            node for node in media_nodes if node['status'] == "FAILED"]

        if failed_items:
            logger.info("Some media failed to process:")
            for item in failed_items:
                logger.info(f"Status: {item['status']}, Errors: {item['mediaErrors']}")
            return False

        if not processing_items:
            logger.info("All media have completed processing.")
            return True

        logger.info("Media still processing. Waiting...")
        time.sleep(poll_interval)
        attempts += 1

    logger.info("Timeout reached while waiting for media processing completion.")
    return False


def check_rohseoul_media(sku, medias):
    if medias:
      filename = medias[0]['image']['url'].rsplit('/', 1)[-1]
      return f'{sku}_0' in filename or filename.startswith('b1_') or '_0_' in filename
    logger.info(f'no media for {sku}')
    return True


def medias_by_variant_id(shop_name, access_token, variant_id):
    product_id = product_id_by_variant_id(shop_name, access_token, variant_id)
    all_medias = medias_by_product_id(shop_name, access_token, product_id)      # sorted by position
    all_media_ids = [m['id'] for m in all_medias]
    all_variants = product_variants_by_product_id(shop_name, access_token, product_id)
    # assert all(check_rohseoul_media(variant['sku'], variant['media']['nodes']) for variant in all_variants), f'suspicious media found in variants of {product_id}: {all_variants}'
    target_variant = [v for v in all_variants if v['id'] == variant_id]
    assert len(target_variant) == 1, f"{'No' if not target_variant else 'Multiple'} target variants: target_variants"
    target_variant = target_variant[0]
    if not target_variant['media']['nodes']:
        variant = variant_by_variant_id(shop_name, access_token, variant_id)
        return [media for media in all_medias if variant['sku'] in media['image']['url']]
    target_media_start_position = all_media_ids.index(target_variant['media']['nodes'][0]['id'])
    # can have multiple variants for the same media e.g. size variations
    all_media_start_positions = sorted(set([all_media_ids.index(variant['media']['nodes'][0]['id']) for variant in all_variants] + [len(all_medias)]))
    target_media_end_position = all_media_start_positions[all_media_start_positions.index(target_media_start_position) + 1]
    return all_medias[target_media_start_position:target_media_end_position]


def medias_by_sku(shop_name, access_token, sku):
    variant_id = variant_id_by_sku(shop_name, access_token, sku)
    return medias_by_variant_id(shop_name, access_token, variant_id)


def variant_by_sku(shop_name, access_token, sku):
    query = """
    {
      productVariants(first: 10, query: "sku:'%s'") {
        nodes {
          id
          title
          product {
            id
          }
        }
      }
    }
    """ % sku
    res = run_query(shop_name, access_token, query)
    return res['productVariants']


def product_id_by_sku(shop_name, access_token, sku):
    res = variant_by_sku(shop_name, access_token, sku)
    if len(res['nodes']) != 1:
        raise Exception(f"{'Multiple' if res['nodes'] else 'No'} variants found for {sku}: {res['nodes']}")
    return res['nodes'][0]['product']['id']


def variant_by_variant_id(shop_name, access_token, variant_id):
    query = """
    {
      productVariant(id: "%s") {
        id
        title
        sku
        media(first: 5) {
          nodes {
            id
          }
        }
      }
    }
    """ % variant_id

    res = run_query(shop_name, access_token, query, {})
    return res['productVariant']


def variant_id_by_sku(shop_name, access_token, sku):
    res = variant_by_sku(shop_name, access_token, sku)
    if len(res['nodes']) != 1:
        raise Exception(f"{'Multiple' if res['nodes'] else 'No'} variants found for {sku}: {res['nodes']}")
    return res['nodes'][0]['id']


def generate_staged_upload_targets(shop_name, access_token, file_names, mime_types):
    query = """
    mutation stagedUploadsCreate($input: [StagedUploadInput!]!) {
      stagedUploadsCreate(input: $input) {
        stagedTargets {
          url
          resourceUrl
          parameters {
            name
            value
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": [{
            "resource": "IMAGE",
            "filename": file_name,
            "mimeType": mime_type,
            "httpMethod": "POST",
        } for file_name, mime_type in zip(file_names, mime_types)]
    }

    res = run_query(shop_name, access_token, query, variables)
    return res['stagedUploadsCreate']['stagedTargets']


def upload_images_to_shopify(staged_targets, local_paths, mime_types):
    for target, local_path, mime_type in zip(staged_targets, local_paths, mime_types):
        if mime_type in ['image/psd']:
            continue
        file_name = local_path.rsplit('/', 1)[-1]
        logger.info(f"  processing {file_name}")
        payload = {
            'Content-Type': mime_type,
            'success_action_status': '201',
            'acl': 'private',
        }
        payload.update({param['name']: param['value']
                       for param in target['parameters']})
        with open(local_path, 'rb') as f:
            logger.debug(f"  starting upload of {local_path}")
            response = requests.post(target['url'],
                                     files={'file': (file_name, f)},
                                     data=payload)
        logger.debug(f"upload response: {response.status_code}")
        if response.status_code != 201:
            logger.error(f'!!! upload failed !!!\n\n{local_path}:\n{target}\n\n{response.text}\n\n')
            response.raise_for_status()


def detach_variant_media(shop_name, access_token, product_id, variant_id, media_id):
    query = """
    mutation productVariantDetachMedia($productId: ID!, $variantMedia: [ProductVariantDetachMediaInput!]!) {
      productVariantDetachMedia(productId: $productId, variantMedia: $variantMedia) {
        product {
          id
        }
        productVariants {
          id
          media(first: 5) {
            nodes {
              id
            }
          }
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "productId": product_id,
        "variantMedia": [{
            "variantId": variant_id,
            "mediaIds": [media_id]
        }]
    }
    return run_query(shop_name, access_token, query, variables)


def product_media_by_file_name(shop_name, access_token, product_id, name):
    medias = medias_by_product_id(shop_name, access_token, product_id)
    for media in medias:
        if name.rsplit('.', 1)[0] in media['image']['url']:
            return media


def assign_image_to_skus(shop_name, access_token, product_id, media_id, variant_ids):
    variants = [variant_by_variant_id(shop_name, access_token, variant_id)
                for variant_id in variant_ids]
    for variant in variants:
        if len(variant['media']['nodes']) > 0:
            detach_variant_media(shop_name, access_token,
                                 product_id,
                                 variant['id'],
                                 variant['media']['nodes'][0]['id'])
    query = """
    mutation productVariantAppendMedia($productId: ID!, $variantMedia: [ProductVariantAppendMediaInput!]!) {
      productVariantAppendMedia(productId: $productId, variantMedia: $variantMedia) {
        product {
          id
        }
        productVariants {
          id
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    variables = {
        "productId": product_id,
        "variantMedia": [{"variantId": vid, "mediaIds": [media_id]} for vid in variant_ids]
    }

    return run_query(shop_name, access_token, query, variables)


def location_id_by_name(shop_name, access_token, name):
    query = '''
    {
      locations(first:10, query:"name:%s") {
        nodes {
          id
        }
      }
    }
    ''' % name
    res = run_query(shop_name, access_token, query)
    res = res['locations']['nodes']
    assert len(res) == 1, f'{"Multiple" if res else "No"} locations found for {name}: {res}'
    return res[0]['id']


def inventory_item_id_by_sku(shop_name, access_token, sku):
    query = '''
    {
      inventoryItems(query:"sku:%s", first:5) {
        nodes{
          id
        }
      }
    }''' % sku
    res = run_query(shop_name, access_token, query)
    res = res['inventoryItems']['nodes']
    assert len(res) == 1, f'{"Multiple" if res else "No"} inventoryItems found for {sku}: {res}'
    return res[0]['id']


def set_inventory_quantity_by_sku_and_location_id(shop_name, access_token, sku, location_id, quantity):
    inventory_item_id = inventory_item_id_by_sku(shop_name, access_token, sku)
    query = '''
    mutation inventorySetQuantities($locationId: ID!, $inventoryItemId: ID!, $quantity: Int!) {
    inventorySetQuantities(
        input: {name: "available", ignoreCompareQuantity: true, reason: "correction",
                quantities: [{inventoryItemId: $inventoryItemId,
                              locationId: $locationId,
                              quantity: $quantity}]}
    ) {
        inventoryAdjustmentGroup {
        id
        changes {
            name
            delta
            quantityAfterChange
        }
        reason
        }
        userErrors {
        message
        code
        field
        }
      }
    }
    '''
    variables = {
        "inventoryItemId": inventory_item_id,
        "locationId": location_id,
        "quantity": quantity
    }
    res = run_query(shop_name, access_token, query, variables)
    if res['inventorySetQuantities']['userErrors']:
        raise Exception(f"Error updating inventory quantity: {res['inventorySetQuantities']['userErrors']}")
    updates = res['inventorySetQuantities']['inventoryAdjustmentGroup']
    if not updates:
        logger.info(f'no updates found after updating inventory of {sku} to {quantity}')
    return updates


def run_query(shop_name, access_token, query, variables=None, method='post', resource='graphql'):
    url = f'https://{shop_name}.myshopify.com/admin/api/2024-07/{resource}.json'
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    data = {
        "query": query,
        "variables": variables
    }
    response = requests.post(url, headers=headers, json=data)
    res = response.json()
    if errors := res.get('errors'):
        raise RuntimeError(f'Error running the query: {errors}\n\n{query}\n\n{variables}')
    return res['data']

def main():
    import os
    from dotenv import load_dotenv
    load_dotenv(override=True)
    print(os.getenv('ACCESS_TOKEN'))
    dirname = r'/Users/taro/Downloads/jpg追加/'
    local_paths = [f'{dirname}{p}' for p in os.listdir(dirname) if 'product_detail_' in p]
    replace_image_files('apricot-studios', os.getenv('ACCESS_TOKEN'), local_paths)


if __name__ == '__main__':
    main()
