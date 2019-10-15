#!/usr/bin/env bash

# ".aisecurity.make_config"
# Program to make config file (~/.aisecurity.json)

if [ ! -d "$HOME/.aisecurity" ] ; then
  mkdir "$HOME/.aisecurity"
else
  read -rp "$HOME/.aisecurity already exists. Overwrite? (y/n): " confirm
  if ! [[ $confirm == [yY] || $confirm == [yY][eE][sS] ]] ; then
    echo "Exiting..." ; exit 1
  fi
fi

cd "$HOME/.aisecurity" || echo "Error: unable to access ~/.aisecurity"
config_path=$(realpath .) || config_path=$(pwd )

echo "Adding aisecurity.json to .aisecurity"
touch "$HOME/.aisecurity/aisecurity.json"

printf '{\n    "key_directory": "%s/keys/",\n    "key_location": "%s/keys/keys_file.json",\n    "database_location": "%s/database/encrypted.json",\n}\n' \
"$config_path" "$config_path" "$config_path" > "$config_path/aisecurity.json"

if [ ! -d "$config_path/database" ] ; then
  mkdir database
  cd "$config_path/database" || echo "Error: unable to access $config_path/database"
  mkdir unknown
  touch encrypted.json
fi

if [ ! -d "$config_path/models" ] ; then
  cd "$config_path" || echo "Error: unable to access $config_path"
  mkdir models
  cd models || echo "Error: unable to access $config_path/models"
  wget -O "facenet_keras.h5" "https://github.com/orangese/aisecurity/blob/v1.0a/models/ms_celeb_1m.h5" || curl "https://github.com/orangese/aisecurity/blob/v1.0a/models/ms_celeb_1m.h5" -o "facenet_keras.h5"
fi


if [ ! -d "$HOME/.aisecurity/keys" ] ; then
  cd "$config_path" || echo "Error: unable to access $config_path"
  mkdir keys
fi