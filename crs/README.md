# CRS

Competitors should place all source code unless instructed otherwise under this folder.

We may build this component out as more of a MockCRS in future iterations.

However, it is intended that competitors will completely replace all code within this folder with their solutions.

The only additional changes to this repository should be to the

- `.github/workflows/crs.yaml`
- `compose.yaml` to reference your specific container/s.
- `crs/README.md` to assist your team with development.
- `crs/src/*` an example of where you could store your actual CRS code.

## AICD

Note that this readme is not a substitute for the original README.md provided by the AIxCC organizers.

### Extending CRS functionality

The interfaces with the various components can be found in [api](./src/py/api).
To interact with the challenge projects, the [api.cp.ChallengeProject](./src/py/api/cp.py) class exposes the relevant
functionality as methods.
The code that interacts with the LLM APIs can be found in [api/llm.py](./src/py/api/llm.py).
To submit vulnerabilities and patches, the code that interfaces with the competition API (cAPI) lives
in [api/submit.py](./src/py/api/submit.py).

To add new code to the CRS, edit the appropriate file in the [pipeline](./src/py/pipeline) folder.

For example, to add code to the vulnerability discovery pipeline:

- add a function in [vuln_discovery.py](./src/py/pipeline/vuln_discovery.py) or a method to the `VulnDiscovery` class
- call the new function in `VulnDiscovery.run`

For debugging, logger output is provided.
By default, only `INFO` and up are printed to the Docker attached tty.
The full logs, including `DEBUG` and logs from underlying libraries such as git commands and network requests to 
litellm, are printed to `/crs_scratch/crs.log`.

The project includes some non-exhaustive type hinting, which is checked through GitHub actions.
It is there to help, not hinder so if it highlights something being wrong, it's likely a potential source of buggy behaviours.
You can run it at any time using `pyright -p crs/src/`

### Setting up the CRS on a new machine

- Install docker engine >= 24.0.5
  - uninstall any potential existing Docker packages by running
    `for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove $pkg; done`
  - Follow https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository
  - Enable managing Docker as a non-root user: https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user
- Install GNU make >= 4.3
  - `sudo apt install make`
- Install mise by following https://mise.jdx.dev/getting-started.html
  - `curl https://mise.run | sh`
  - `echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc`
  - `echo 'export PATH="$HOME/.local/share/mise/shims:$PATH"' >> ~/.bash_profile`
  - if you cannot run `mise --version` then uninstall using `~/.local/bin/mise implode` and start again :/
- We will supply you with an SSH key which you will need to use to pull and push to the repo: 
  - move the key to the `~/.ssh/` directory
  - `chmod 600 ~/.ssh/id_rsa_aicc`
  - `eval "$(ssh-agent -s)"`
  - `ssh-add ~/.ssh/id_rsa_aicc`
- Run `sudo sysctl -w vm.mmap_rnd_bits=28` to avoid issues with address randomisation
  (see https://github.com/aixcc-sc/cp-sandbox/pull/28 and linked issues for extra details)
- Clone the repo by running `git clone git@github.com:aixcc-sc/asc-crs-mindrake.git`
- `cd` into repo directory and run `mise install` to install dependencies
- run `cp sandbox/example.env sandbox/env` and modify `sandbox/env` as follows:
  - generate a new personal access token (PAT) (https://github.com/settings/tokens) with `read:packages` permissions.
  - authorise the token by clicking "Configure SSO" next to it and then "aixcc-sc".
  - include our GitHub username (`auth0-660bd3c14d2d6436de9169f3_aixcc`) and personal access token in the
    `GITHUB_USER` and `GITHUB_TOKEN` variables, respectively, in the `env` file
  - fill in API keys for the LLMs (`ANTHROPIC_API_KEY`, `AZURE_API_KEY`, `OPENAI_API_KEY`)
  - if you are usure what info you should put there, please let us know
- (OPTIONAL) To enable [LangSmith](https://docs.smith.langchain.com/) integration to help with debugging LangChain:
  - run `cp crs/src/env.example crs/src/env`
  - modify `crs/src/env` as follows:
    - log into https://smith.langchain.com, create a PAT, and add it to `LANGCHAIN_API_KEY`
    - to enable logging, such as when changing or debugging LLM code, change `LANGCHAIN_TRACING_V2` to `true`
    - change it back to `false` when no longer required to avoid using up the limited quota on our free account
- run `docker login -u auth0-660bd3c14d2d6436de9169f3_aixcc -p <your pat> ghcr.io` to access the competition images
  - _Note_: challenge images are handled by the `load-cp-images` container and are placed into the `dind` cache
    (`dind_cache`).
    - if you want to run Docker commands inside the `dind` container, uncomment the port bindings for `dind`
      in [compose_local_overrides.yaml](../compose_local_overrides.yaml) and run `make up`.
      Prefixing Docker commands with `DOCKER_HOST=tcp://localhost:2375` will let you run commands using the Docker
      instance inside the containers, e.g. `DOCKER_HOST=tcp://localhost:2375 docker images` to check which CP images are
      available.
- run `c=crs make up-attached` to bring up th CRS server with attached output stream
  - this will bring up the other containers in the background and keep them running after the CRS exits, including:
    - LiteLLM proxy (port 8081 on host)
    - cAPI (scoring server API, port 8080 on host)
    - dind (Docker-in-Docker)
  - to make re-running the CRS easier, consider adding `alias crs="c=crs make up-attached"` to your `~/.bashr`/`~/.zshrc`/etc.


### Development workflow

1. Do any work on new branches called `<name>/<short description>`.
2. When you want it tested against the GitHub actions, open a draft pull request (PR) into the `main` branch.
3. When it's ready to be merged into `main`, press the "Ready for review" button.
4. Ask for a quick code review in the channel to
   1. get a second pair of eyes on your code;
   2. make changes visible to everyone else so there is less potential for toe stepping/duplicate effort.
5. Once you had some peer feedback, hit merge on the GH PR if all tests are green and there's no comments saying you
   should make changes.
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
- Nginx CP: https://github.com/aixcc-sc/challenge-004-nginx-cp
  - Contains:
    - https://github.com/aixcc-sc/challenge-004-nginx-source
      - Source code for Nginx proxy (in C)
