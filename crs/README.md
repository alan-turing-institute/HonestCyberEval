# CRS

Competitors should place all source code unless instructed otherwise under this folder.

We may build this component out as more of a MockCRS in future iterations.

However it is intended that competitors will completely replace all code within this folder with their solutions.

The only additional changes to this repository should be to the

- `.github/workflows/crs.yaml`
- `compose.yaml` to reference your specific container/s.
- `crs/README.md` to assist your team with development.
- `crs/src/*` an example of where you could store your actual CRS code.

## AICD

Note that this readme is not a substitute for the original README.md provided by the AIxCC organizers. 

### Setting up the CRS on a new machine
- Install docker engine >= 24.0.5
  - uninstall any potential existing Docker packages by running `for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove $pkg; done`
  - Follow https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository
- Install GNU make >= 4.3
  - `sudo apt install make`
- Install mise by following https://mise.jdx.dev/getting-started.html 
  - `curl https://mise.run | sh`
  - `echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc`
  - `echo 'export PATH="$HOME/.local/share/mise/shims:$PATH"' >> ~/.bash_profile`
  - if you cannot run `mise --version` then uninstall using `~/.local/bin/mise implode` and start again :/
- Clone this repo
- `cd` into repo directory and run `mise install` to install dependencies
- run `make cps` to pull the CP repos listed in [cp_config.yaml](..%2Fcp_config.yaml)
  - If you get authentication issues, you should use the private SSH key linked to our AIxCC GitHub Account.
    - move the key to the `~/.ssh/` directory
    - `chmod 600 ~/.ssh/id_rsa_aicc`
    - `eval "$(ssh-agent -s)"`
    - `ssh-add ~/.ssh/id_rsa_aicc`
- `cd` into the CP folders in `cp_root` and run `make docker-pull` in each to pull the image used to build and test the CP
  - when running containers locally, your Docker Daemon is exposed inside the container, so pulling the image will make it available inside the CRS container through the `dind` (Docker-in-Docker) container  
- run `make build` to build docker images 
  - if you face issues regarding `yq` not installed, then run the following and try again
    - `wget https://github.com/mikefarah/yq/releases/download/v4.44.1/yq_linux_amd64`
    - `chmod +x yq_linux_amd64`
    - `mv yq_linux_amd64 yq`
    - `sudo mv  yq  /bin`
- run `cp sandbox/example.env sandbox/env` and modify `sandbox/env` as follows: 
  - fill in any API keys for the LLMs (e.g., OpenAI key)
  - include our GitHub username and personal access token in the `GITHUB_USER` and `GITHUB_TOKEN` variables in the `env` file
  - if you are usure what info you should put there, please let us know
- To start LiteLLM proxy (port 8081 on host) and cAPI (scoring server API, port 8080 on host), run `make up`
  - if you get an error regarding the "docker.sock" file you might need to run `sudo chmod 777 /var/run/docker.sock`
- To run only the CRS server with attached output stream run `c=crs make up-attached`

### Development workflow
1. Do any work on new branches called `<name>/<short description>`.
2. When you want it tested against the GitHub actions, open a draft pull request (PR) into the `main` branch.
3. When it's ready to be merged into `main`, press the "Ready for review" button.
4. Ask for a quick code review in the channel to 
   1. get a second pair of eyes on your code;
   2. make changes visible to everyone else so there is less potential for toe stepping/duplicate effort.
5. Once you had some peer feedback, hit merge on the GH PR if all tests are green and there's no comments saying you should make changes.
6. Delete branch and start any new work from _1._ after you pull the latest changes to main.

### AIxCC repos

- CRS Sandbox (from which this repo was cloned): https://github.com/aixcc-sc/crs-sandbox.git
  - Changes to the CRS Sandbox will make their way to our repo as pull requests
  - If you encounter issues with the AIxCC provided code, raise an issue here 
- Competition API (cAPI): https://github.com/aixcc-sc/capi.git
  - The API that the CRS must submit vulnerabilities and patches to
- Jazzer: https://github.com/aixcc-sc/jazzer.git
  - A Java fuzzer with sanitizers compatible with AIxCC
  
#### AIxCC Challenge projects
- CP Sandbox: https://github.com/aixcc-sc/cp-sandbox.git
  - The generic structure of a CP repo
- Mock CP: https://github.com/aixcc-sc/mock-cp.git
  - A very basic CP
  - Contains:
    - Mock CP Source: https://github.com/aixcc-sc/mock-cp-src.git
      - Source code for Mock CP (in C)
- Jenkins CP: https://github.com/aixcc-sc/challenge-002-jenkins-cp.git
  - CP for Jenkins software
  - Contains:
    - Jenkins CP Source: https://github.com/aixcc-sc/challenge-002-jenkins-source.git
      - Source code for Jenkins CP (in Java)
    - Jenkins Plugin: https://github.com/aixcc-sc/challenge-002-jenkins-plugins.git
      - Repo with a plugin used by the Jenkins CP
- Linux Kernel CP: https://github.com/aixcc-public/challenge-001-exemplar.git
  - Contains:
    - Linux Kernel CP Source: https://github.com/aixcc-public/challenge-001-exemplar-source.git
      - Source code for Linux kernel (in C)

