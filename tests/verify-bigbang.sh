#!/bin/bash

echo "Verifying Big Bang reconcilation - Timeout at 60 minutes\n\n"

for n in {1..60}
do
    out=$(kubectl get gitrepositories,ks,hr -A | grep 'False\|Unknown' | cat)

    if [[ "$out" = "" ]]; then break; fi
    
    echo "Waiting for Big Bang to reconcile ... (minute $n of 60)"
    
    
    if [ $((n%3)) == "0" ]; then kubectl gitrepositories,get ks,hr -A; fi
    
    echo "-----"

    sleep 60
done

kubectl gitrepositories,get ks,hr -A

out=$(kubectl get ks,hr -A | grep 'False\|Unknown' | cat)

if [[ "$out" = "" ]]; then echo "SUCCESS"; exit 0; fi

echo "Reconciliation Timed Out"
