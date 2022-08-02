from re import sub
from sys import stdout
from rich import print as rprint
import os
import subprocess
from subprocess import PIPE, Popen, STDOUT
import pathlib
import logging
from util.io import *
from util.streams import Stream

log_format = '%(asctime)s %(filename)s: %(message)s'
logging.basicConfig(filename='app.log', level=logging.DEBUG, format=log_format, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

_default_dsop_rke2_repo = "https://github.com/p1-dsop/dsop-rke2"

class BigBang_Stream (Stream):

    def generate_root_key_and_cert (self):
        '''
        Generates openssl ca.key and ca.crt files in the BigBang project directory.
        '''

        logger.debug ("Generating root (CA) cert")
        pdir = self.get_project_dir()

        if os.path.isfile (f"{pdir}/ca.key"):
            cout_error_and_exit ("Certificate Authority files already exist! Exiting.")

        self._generate_private_key("ca.key", "2048", cwd=pdir)
        self._generate_root_certificate ("ca.key", "ca.crt", cwd=pdir)
        
        logger.debug ("Successfully created root (CA) cert")

        cout_success ("Successfully generated root keys and certificates!")

        cout_success (f"The following files have been written:")
        cout_success (f"\t- ca.crt is the public certificate that should be imported in your browser.")
        cout_success (f"\t- ca.key is the private key that will be used to generate domain certs.")

        cout_success (f"Next step: Import ca.crt in your browser")

    def generate_domain_key_and_cert (self, domain:str):
        '''
        Generate openssl <domain>.key and <domain>.crt files in the BigBang project directory.
        '''

        logger.debug (f"Generating domain cert for <{domain}>")
        pdir = self.get_project_dir()
        
        if os.path.isfile (f"{pdir}/ca.key") == False:
            cout_error_and_exit ("Certificate Authority files missing! Exiting.")

        self._generate_private_key(f"{domain}.key", "2048", cwd=pdir)
        self._generate_domain_signing_request (domain, cwd=pdir)
        self._generate_domain_extension_config (domain, cwd=pdir)
        self._generate_domain_signed_certificate (domain, cwd=pdir)
        self._domain_cert_file_cleanup (domain, cwd=pdir)

        logger.debug (f"Successfully created domain cert for <{domain}>")
        cout_success (f"\tYou can now use {domain}.key and {domain}.crt in your web server.")
        cout_success (f"\tDon't forget that you must import ca.crt in your browser to make it accept the certificate.")

    def get_domain_key_and_cert_base64 (self, hostname):
        '''
        Returns a tuple of of the key and cert file for <hostname> in base64 string.
        '''       

        istio_gw_key = run_processes_piped (
            ['cat', f"{hostname}.key"],
            ['base64', '-w0'],
            self.get_project_dir(),
        ).replace('\n','\n             ').strip()

        istio_gw_crt = run_processes_piped (
            ['cat', f"{hostname}.crt"],
            ['base64', '-w0'],
            self.get_project_dir(),
        ).replace('\n','\n             ').strip()

        return f"{istio_gw_key}", f"{istio_gw_crt}"

    def store_key_and_cert_in_akv(self):
        pass

    def get_gpg_fingerprint (self, gpg_key_name:str, create_if_needed:bool = False):
        '''
        Returns the gpg fingerprint for the provided key name. Optionally create the gpg key if it does not exist.

        Note: This command uses gpg-key-gen.sh script provided in the container. Could not get gpg to operate without user interaction when executing via PyBuilder app.
        '''
        
        if not self._gpg_key_name_exists(gpg_key_name):
            if create_if_needed:
                self._generate_gpg_key_complete(gpg_key_name)
            else:
                cout_error_and_exit (f"GPG Key {gpg_key_name} does not exist. Exiting")
        else:
            logger.info("gpg keys exist already. skipping creation.")

        fingerprint = self._get_gpg_fingerprint(gpg_key_name)
    
        return fingerprint

    def generate_gpg_secret_file (self, fingerprint:str):
        '''
        Generates the gpg secret file - this later becomes a secret in Kubernetes
        '''
        command = f"gpg --export-secret-key --armor {fingerprint}".split()
        
        fout = open(f"bigbangkey.asc", "w+")
        subprocess.run(command, stdout=fout)
        fout.close()

    def sops_encrypt(self, file:str, cwd:str=""):
        '''
        Encryptes provided filename in place using SOPS. Exits on error.
        '''
        command = f"sops --encrypt --in-place {file}".split()
        res = subprocess.run(command, cwd=cwd, capture_output=True, encoding='UTF-8')

        cout_success(f"{res.stdout}")

        if (res.returncode != 0):
            cout_error_and_exit(f"{res.stderr}")

    def exec_kubectl_cmd(self, cmd=str):
        '''
        kubectl passthrough. Executes an arbitrary kubectl command. 
        Requires kubeconfig to be set.
        Exits on Error code.
        '''
        command = f"kubectl {cmd}".split()
        res = subprocess.run(command, capture_output=True, encoding='UTF-8')

        cout_success(f"{res.stdout}")

        if (res.returncode != 0):
            cout_error (f"{res.stderr}")

    def install_flux (self, ib_user:str, ib_pat:str, ib_email:str):
        '''
        Installs flux using the bigbang install_flux.sh script.
        '''
        command = f"./scripts/install_flux.sh --registry-username {ib_user} --registry-password {ib_pat} --registry-email {ib_email} -w 600".split()

        flux_dir = f"{self.get_scripts_dir()}/bigbang-for-flux"
        #print (flux_dir)
        #print (command)

        #res = subprocess.run(command, capture_output=True, encoding='UTF-8', cwd=flux_dir)
        res = subprocess.run(command, cwd=flux_dir)

#        cout_success(f"{res.stdout}")
#        cout_error(f"{res.stderr}")

    # --------------------------------

    def _generate_private_key (self, new_key_file:str="ca.key", key_len:str="2048", cwd:str=""):
        command = ["openssl", "genrsa", "-out", new_key_file, key_len]
        try:           
            subprocess.run (command, cwd=cwd, check=True)

            cout_success (f"Success! Generated private key - {new_key_file}")
        except Exception as e:
            logger.debug(f"Error generating private key: {e}")
            cout_error_and_exit(f"Error generating private key: {e}")    

    def _generate_root_certificate (self, key_file:str="ca.key", new_cert_file:str="ca.crt", cwd:str=""):
        
        # openssl req -x509 -new -nodes -subj "/C=US/O=_Development CA/CN=Development certificates" -key ca.key -sha256 -days 3650 -out ca.crt

        command_front = f"openssl req -x509 -new -nodes -subj".split()
        command_mid   = "/C=US/O=_Development CA/CN=Development certificates"
        command_back  = f"-key {key_file} -sha256 -days 3650 -out {new_cert_file}".split()
        
        command = command_front + [command_mid] + command_back

        try:
            subprocess.run (command, cwd=cwd, check=True)

            cout_success (f"Success! Generated Root Certificate - {key_file}")

        except Exception as e:
            logger.debug(f"Error _generate_root_certificate: {e}")
            cout_error_and_exit(f"Error _generate_root_certificate: {e}")

    def _generate_domain_signing_request (self, domain:str, cwd:str=""):
        
        command_front = f"openssl req -new -subj".split()
        command_mid   = f"/C=US/O=Local Development/CN={domain}"
        command_back  = f"-key {domain}.key -out {domain}.csr".split()

        # command = f"openssl req -new -subj \"/C=US/O=Local Development/CN={domain}\" -key \"{domain}.key\" -out \"{domain}.csr\"".split()       

        command = command_front + [command_mid] + command_back

        try:
            run_process(command, cwd=cwd)
            cout_success (f"Success! _generate_domain_signing_request") 

        except Exception as e:
            logger.debug(f"Error _generate_domain_signing_request: {e}")
            cout_error_and_exit(f"Error _generate_domain_signing_request: {e}")

    def _generate_domain_extension_config (self, domain:str, cwd:str=""):

        ext_string = (""
        "authorityKeyIdentifier=keyid,issuer\n"
        "basicConstraints=CA:FALSE\n" 
        "keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment\n"            
        "extendedKeyUsage = serverAuth, clientAuth\n"
        "subjectAltName = @alt_names\n"
        "[alt_names]\n"             
        f"DNS.1 = {domain}\n"
        f"DNS.2 = *.{domain}")

        try: 
            fout = open(f"{domain}.ext", "w+")
            subprocess.run(['echo',ext_string], stdout=fout)
            fout.close()
        except Exception as e:
            cout_error_and_exit (f"Error: _generate_domain_extension_config {e}")

    def _generate_domain_signed_certificate (self, domain:str, cwd:str=""):
        command_str = (""
        "openssl x509 -req "
        f"-in {domain}.csr -extfile {self.base_dir}/{domain}.ext "
        f"-CA ca.crt -CAkey ca.key -CAcreateserial -out {domain}.crt -days 365 -sha256")

        command = command_str.split()

        try:
            run_process(command, cwd=cwd)
            cout_success (f"Success! _generate_domain_signed_certificate")
        except Exception as e:
            logger.debug(f"Error _generate_domain_signed_certificate: {e}")
            cout_error_and_exit(f"Error _generate_domain_signed_certificate: {e}")

    def _domain_cert_file_cleanup (self, domain:str, cwd:str=""):
        command = f"rm -rf {self.get_project_dir()}/{domain}.csr {self.base_dir}/{domain}.ext".split()

        try:
            run_process(command, shell=True)
            cout_success (f"Success! _domain_cert_file_cleanup")  
        except Exception as e:
            logger.debug(f"Error _domain_cert_file_cleanup: {e}")
            cout_error (f"{command}")
            cout_error_and_exit(f"Error _domain_cert_file_cleanup: {e}")

    def _gpg_key_name_exists (self, gpg_key_name:str):
        command = f"gpg -K {gpg_key_name}".split()
        try:
            subprocess.run(command, check=True)
            return True
        except Exception as e:
            return False

    def _generate_gpg_key (self, gpg_key_name:str):
        gen_cmd = f"gpg --quick-generate --batch --passphrase '.' {gpg_key_name}".split()
        print (gen_cmd)
        run_process(gen_cmd)

    def _generate_gpg_key_complete (self, gpg_key_name:str):
        gen_cmd = f"./gpg-key-gen.sh {gpg_key_name}".split()
        run_process(gen_cmd, cwd=self.get_scripts_dir())


    def _get_gpg_fingerprint (self, gpg_key_name:str):
        gpg_get_key_cmd = f"gpg -K {gpg_key_name}".split()
        sed_cmd = f"sed -e 's/ *//;2q;d;'"

        fingerprint = run_processes_piped (gpg_get_key_cmd, sed_cmd, encoding='UTF-8')
        #print (f"{fingerprint}")
        return fingerprint.strip()

    def _gpg_quick_add_fingerprint (self, fingerprint:str):
        command = f"gpg --quick-add-key --batch --yes --no-tty --passphrase '.' {fingerprint} rsa4096 encr".split()
        run_process(command)

if __name__ == '__main__':
    _stream = Stream()
    _stream.run_console()
