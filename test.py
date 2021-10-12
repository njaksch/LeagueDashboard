import os


def saveSnapshot(gameJson, dir_name):
    # dirList = os.listdir('records')
    # if len(dirList) == 0:
    #     dir_name = '1'
    # else:
    #     dir_name = str(int(dirList[-1]) + 1)
    fileList = os.listdir('records/{dir}'.format(dir=dir_name))
    if len(fileList) == 0:
        file_name = '1'
    else:
        file_name = str(int(fileList[-1].replace('.json', '')) + 1)
    path = 'records/{dir}/{file}.json'.format(dir=dir_name, file=file_name)
    file = open(path, 'w')
    file.write(str(gameJson))

