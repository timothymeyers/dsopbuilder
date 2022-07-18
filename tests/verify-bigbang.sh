#!/bin/bash

echo "Verifying Big Bang reconcilation - Timeout at 30 minutes\n\n"

for n in {1..30}
do
    kubectl get ks,hr -A | grep 'False\|Unknown' &> /dev/null && :
    if [[ $? -eq 1 ]]; then break; fi
    
    echo "Waiting for Big Bang to reconcile ... (minute $n of 30)"
    kubectl get ks,hr -A
    
    if [ $((n%5)) == "0" ]; then echo "----- Full -----"; kubectl get ks,hr -A; fi
    
    echo "-----"

    sleep 60
done

kubectl get ks,hr -A | grep 'False\|Unknown' &> /dev/null && :
if [[ $? -eq 1 ]]; then exit 1; fi

#python3 main.py bb verify
kubectl get ks,hr -A

exit 0
