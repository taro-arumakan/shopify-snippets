import os
from dotenv import load_dotenv
from shopify_utils import update_product_description_metafield, product_id_by_title
from google_utils import gspread_access, get_sheet_index_by_title

load_dotenv(override=True)
SHOPNAME = 'apricot-studios'
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print(ACCESS_TOKEN)
GOOGLE_CREDENTIAL_PATH = os.getenv('GOOGLE_CREDENTIAL_PATH')

GSPREAD_ID = '1yVzpgcrgNR7WxUYfotEnhYFMbc79l1O4rl9CamB2Kqo'
SHEET_TITLE = 'Products Master'


def get_product_description(desc, care, size, material, origin):

  res = {
    'type': 'root',
    'children': [{'children': [{'type': 'text', 'value': '商品説明'}], 'level': 3, 'type': 'heading'},
                {'children': [{'type': 'text', 'value': desc}], 'type': 'paragraph'},
                {'children': [{'type': 'text', 'value': '使用上の注意'}], 'level': 3, 'type': 'heading'},
                {'children': [{'type': 'text',
                              'value': care}],
                'type': 'paragraph'},
                {'children': [{'type': 'text', 'value': ''}], 'type': 'paragraph'},
                {'children': [{'type': 'text', 'value': 'サイズ'}], 'level': 3, 'type': 'heading'},
                {'children': [{'type': 'text', 'value': size}], 'type': 'paragraph'},
                {'children': [{'type': 'text', 'value': '素材'}], 'level': 3, 'type': 'heading'},
                {'children': [{'type': 'text', 'value': material}], 'type': 'paragraph'},
                {'children': [{'type': 'text', 'value': '原産国'}], 'level': 3, 'type': 'heading'},
                {'children': [{'type': 'text', 'value': origin}], 'type': 'paragraph'}],
  }
  return res


def main():
    sheet_index = get_sheet_index_by_title(GOOGLE_CREDENTIAL_PATH, GSPREAD_ID, SHEET_TITLE)
    worksheet = gspread_access(GOOGLE_CREDENTIAL_PATH).open_by_key(GSPREAD_ID).get_worksheet(sheet_index)
    rows = worksheet.get_all_values()

    for row in rows[1:]:
      title = row[1].strip()
      print(f'processing {title}')
      if not title:
         continue
      product_id = product_id_by_title(SHOPNAME, ACCESS_TOKEN, title)

      desc = row[6]
      care = row[8]
      material = row[10]
      size = row[12]
      origin = row[13]

      product_description = get_product_description(desc, care, size, material, origin)
      res = update_product_description_metafield(SHOPNAME, ACCESS_TOKEN, product_id, product_description)
      import pprint
      pprint.pprint(res)


if __name__ == '__main__':
    main()
