# LLM Bench (working title)

TODO: description

## Setup

- Install dependencies:

  ```shell
  sudo apt install make git-lfs
  ```

- [Install `yq`](https://github.com/mikefarah/yq?tab=readme-ov-file#install)
  - E.g.:

    ```shell
    sudo snap install yq
    ```

- To avoid issues with address randomisation, run:

  ```shell
  sudo sysctl vm.mmap_rnd_bits=28
  echo "vm.mmap_rnd_bits=28" | sudo tee -a /etc/sysctl.conf
  ```

- Set up the environment variables and API keys:
  - Rename the `config/example.env` file:

  ```shell
  cp config/example.env config/env
  ```

  - Generate a new personal access token (PAT) (<https://github.com/settings/tokens>) with `read:packages` permissions.
    Fill in the `GITHUB_USER` and `GITHUB_TOKEN` values.
  - Fill in API keys for the LLM(s) that are to be evaluated (`ANTHROPIC_API_KEY`, `AZURE_API_KEY`, `OPENAI_API_KEY`).
  - For Vertex models, populate the [`config/vertex_key.json`](config/vertex_key.json) file.
    - to make git ignore this change and avoid any accidental commits, run:

      ```shell
      git update-index --skip-worktree sandbox/litellm/vertex_key.json
      ```

  - Generate an SSH key and upload the generated key to your GitHub account.

  - (Optional) Rename the `config/example.crs.env` file, which controls logging:

  ```shell
  cp config/example.crs.env config/crs.env
  ```

### Docker

The evaluation runs as a collection of Docker containers.
If Docker is unavailable, installing it by following the [documentation](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository).
Then, enable [managing Docker as a non-root user](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user).

To be able to pull Docker images for the challenge projects, log into `ghcr.io` using your PAT, run:

  ```shell
  echo "<token>" | docker login ghcr.io -u <user> --password-stdin
  ```

replacing `<user>` and `<token>` with your generated PAT.

The challenge projects are run using Docker-in-Docker.
Challenge images are handled by the `load-cp-images` container and are placed into the `dind` cache volume.
If you want to run Docker commands inside the `dind` container, uncomment the port bindings for `dind` in
[compose.yaml](./compose.yaml).
Prefixing Docker commands with `DOCKER_HOST=tcp://localhost:2375` will let you run commands using the Docker instance
inside the containers, e.g. `DOCKER_HOST=tcp://localhost:2375 docker images` to check which CP images are available.

```shell
export DOCKER_HOST=tcp://127.0.0.1:2375
docker logs <container name>
```

## Running the evaluation

First, configure which challenge project should be downloaded by (un)commenting the appropriate entries in
[`config/cp_config.yaml`](./config/cp_config.yaml).

Load the images for the projects using:

```shell
c=load-cp-images make up-attached
```

Finally, run the evaluation using `docker compose run --rm crs exploit.py --model=<model> -T cp=<challenge project> -S max_iterations=<num>` e.g.

For example:

```shell
docker compose run --rm crs exploit.py --model=openai/o1 -T cp=nginx-cp-full
```

will run the `mock-cp` project with 8 reflexion loops. The first run will be slower as it will patch and build multiple copied of the project.

## Contributing

### Dependencies

Development dependencies are listed in [`pyproject.toml`](./pyproject.toml).
To install all dependencies for development, run:

```shell
pip install -e .[dev]
```

Dependencies for the evaluation image are defined in [`sandbox/crs/pyproject.toml`](./sandbox/crs/pyproject.toml).

The project uses [`pip-tools`](https://github.com/jazzband/pip-tools) to manage dependencies.

#### Tooling

The project includes some non-exhaustive type hinting, which is checked through GitHub actions. It is there to help, not
hinder so if it highlights something being wrong, it's likely a potential source of buggy behaviours. You can run it at
any time using `pyright -p crs/src/`. It also includes `isort` and `black` to autoformat your code. You can run these at
any time using `isort crs/src` and `black crs/src`.

Black, isort, and pyright are checked on the CI pipeline but will not block a merge.

#### Pre-commit

This repository has a [.pre-commit-config.yaml](./.pre-commit-config.yaml) file for assisting with local development.

You can install the command-line tool by going [here](https://pre-commit.com/#install).

#### VSCode

If you're using VSCode, you can use extensions to automate the process (which should show up as recommended):

- <https://marketplace.visualstudio.com/items?itemName=ms-python.isort>
- <https://marketplace.visualstudio.com/items?itemName=ms-python.black-formatter>
- <https://marketplace.visualstudio.com/items?itemName=ms-python.vscode-pylance> (includes pyright)

The `.vscode` folder contains a sample settings file. Run `cp .vscode/settings.json.sample .vscode/settings.json` to use
the settings. Modify [.vscode/settings.json](./.vscode/settings.json) according to the comments to get autoformatting on
save.

### Project structure

The interfaces with the various components can be found in [api](sandbox/crs/src/api).
To interact with the challenge projects, the [api.cp.ChallengeProject](sandbox/src/api/cp.py) class exposes the relevant
functionality as methods.
The code that interacts with the LLM APIs can be found in [api/llm/](sandbox/src/api/llm).

Vulnerability discovery is in [pipeline](sandbox/src/pipeline) folder.

For debugging, logger output is provided. By default, only `INFO` and up are printed to the Docker attached tty. The
full logs, including `DEBUG` and logs from underlying libraries such as git commands and network requests to litellm,
are printed to `/crs_scratch/crs.log`.

## OLD

### Data Sharing & Volumes

A CRS will find the CPs under evaluation in the volume indicated by the environment variable `${CP_ROOT}`. The volume
indicated by the environment variable `${CRS_SCRATCH_SPACE}` will be writable by the CRS and CPs. Moreover, this volume
can be shared among the CRS services as a shared file system. It is the responsibility of the CRS developers to ensure
that use of this shared volume is coordinated between its services to prevent data corruption via collisions or race
conditions. No other folders or volumes will be shared between containers for competitor use during competition.

### Using Make

A Makefile has been provided with a number of a commands to make it easy to clone the exemplar repos, stand up the
environment, and a variety of other actions.

Copy `sandbox/example.env` to `sandbox/env` and replace the variables with your own for local development.

`make cps` - clones the exemplar challenges into local `./cp_root` folder (the source folder for `${CP_ROOT}`)
`make up` - brings up the development CRS Sandbox, you can visit <http://127.0.0.1:8080/docs> to see the iAPI OpenAPI
spec. `make down` - tears down the development CRS Sandbox

See [Makefile](./Makefile) for more commands

`make force-reset` - performs a full Docker system prune of all local docker containers, images, networks, and volumes.
This can be useful if you accidentally orphaned some docker process or other resources.

#### AIxCC Challenge projects

- CP Sandbox: <https://github.com/aixcc-sc/cp-sandbox.git>
  - The generic structure of a CP repo
- Mock CP: <https://github.com/aixcc-sc/mock-cp.git>
  - A very basic CP
  - Contains:
    - Mock CP Source: <https://github.com/aixcc-sc/mock-cp-src.git>
      - Source code for Mock CP (in C)
- Jenkins CP: <https://github.com/aixcc-sc/challenge-002-jenkins-cp.git>
  - CP for Jenkins software
  - Contains:
    - Jenkins CP Source: <https://github.com/aixcc-sc/challenge-002-jenkins-source.git>
      - Source code for Jenkins CP (in Java)
    - Jenkins Plugin: <https://github.com/aixcc-sc/challenge-002-jenkins-plugins.git>
      - Repo with a plugin used by the Jenkins CP
- Linux Kernel CP: <https://github.com/aixcc-public/challenge-001-exemplar.git>
  - Contains:
    - Linux Kernel CP Source: <https://github.com/aixcc-public/challenge-001-exemplar-source.git>
      - Source code for Linux kernel (in C)
- Nginx CP: <https://github.com/aixcc-sc/challenge-004-nginx-cp>
  - Contains:
    - <https://github.com/aixcc-sc/challenge-004-nginx-source>
      - Source code for Nginx proxy (in C)
