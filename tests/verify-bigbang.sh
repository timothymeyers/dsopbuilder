#!/bin/bash

echo "Verifying Big Bang reconcilation - Timeout at 30 minutes\n\n"

for n in {1..30}
do
    python3 main.py bb verify | grep 'False\|Unknown' &> /dev/null && :
    if [[ $? -eq 1 ]]; then break; fi

    echo "Waiting for Big Bang to reconcile ... (minute $n of 30)"
    sleep 60
done

python3 main.py bb verify | grep 'False\|Unknown' &> /dev/null && :
if [[ $? -eq 1 ]]; then exit 1; fi

python3 main.py bb verify
#kubectl get ks,hr -A

exit 0
