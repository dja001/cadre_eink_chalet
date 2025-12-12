
def get_todo_list():

    import os
    import dropbox

    access_token = os.getenv('DROPBOX_API_TOKEN')
    if access_token is None:
        raise ValueError('Pleas load dropbox api token in env before running this script')
    
    dbx = dropbox.Dropbox(access_token)
    
    metadata, res = dbx.files_download("/listes/fermeture_du_chalet.txt")
    #print(metadata)
    #print(res)
    #print(res.content)
    #f.write(res.content)

    text = res.content.decode("utf-8")
    lines = text.splitlines()

    print(lines)
    



if __name__ == '__main__' :

    get_todo_list()
