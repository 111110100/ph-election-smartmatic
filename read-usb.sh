#!/usr/bin/env bash
# run 'screen' and run this script
# usbmount package must be installed and
# setup to automatically mount usb drives

# load environment variables
if ! [ -f .env ]; then
    echo ".env file not found!"
    exit 1
fi

export $(grep -v '^#' .env | xargs)

# location of working director
if [[ -z ${WORKING_DIR} ]]; then
    echo "WORKING_DIR variable not defined"
    return 1
fi
# location of the key file
if [[ -z ${KEYFILE} ]]; then
    echo "KEYFILE variable not defined"
    return 1
fi
# username on the server
if [[ -z {USERNAME} ]]; then
    echo "USERNAME variable not defined"
    return 1
fi
# IP or hostname of the server
if [[ -z ${SERVER} ]]; then
    echo "SERVER variable not defined"
    return 1
fi
# Folder where to put the files on the server
if [[ -z ${FOLDER} ]]; then
    echo "FOLDER variable not defined"
    return 1
fi
# disable screen saver
setterm -blank 0

mkdir -p ${WORKING_DIR}/tmp ${WORKING_DIR}/archive ${WORKING_DIR}/static

while :
do
    d=`date +"%m-%d-%y--%H-%M"`
    dt=`date +"%c"`

    if ! ls /dev/sdb1 2> /dev/null; then
        echo -ne "${dt} - Waiting for USB drive...\r"
    else
        echo
        echo "==========> mounting USB..."
        mount -o ro /dev/sdb1 /mnt

        echo "==========> Moving previous results files..."
        mv ${WORKING_DIR}/results* ${WORKING_DIR}/tmp
        echo

        echo "==========> Creating new folder..."
        mkdir -p ${WORKING_DIR}/archive/${d}
        echo

        echo "==========> Copying files..."
        cp -fpv /mnt/* ${WORKING_DIR}/archive${d}
        echo

        umount /mnt
        echo "*********************************"
        echo "*********************************"
        echo "*   USB DRIVE SAFE TO REMOVE!   *"
        echo "*********************************"
        echo "*********************************"
        echo -ne '\007'
        echo -ne "\a"

        echo "==========> Decompressing results..."
        lzop -d -N -f -p<${WORKING_DIR} ${WORKING_DIR}/archive/${d}/*.lzo
        echo

        echo "==========> Generating results..."
        python3 batch_generate.py all
        echo

        echo "==========> Uploading to server..."
        rm -f ${WORKING_DIR}/results.zip
        zip -9rm ${WORKING_DIR}/results.zip ${WORKING_DIR}/static/*.csv ${WORKING_DIR}/static/*.json
        scp -i $KEYFILE ${WORKING_DIR}/results.zip $USERNAME@$SERVER:$FOLDER
        echo

        echo "==========> Deleting previous results..."
        rm -rf ${WORKING_DIR}/tmp/* &
        echo
    fi

    sleep 1s
done