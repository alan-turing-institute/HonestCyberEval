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
  - Rename the `.env.example` file:

  ```shell
  cp .env.example .env
  ```

  - Generate a new personal access token (PAT) (<https://github.com/settings/tokens>) with `read:packages` permissions.
    Fill in the `GITHUB_USER` and `GITHUB_TOKEN` values.
  - Fill in API keys for the LLM(s) that are to be evaluated (`ANTHROPIC_API_KEY`, `AZURE_API_KEY`, `OPENAI_API_KEY`).
  - For Vertex models, populate the [`config/vertex_key.json`](config/vertex_key.json) file.
    - to make git ignore this change and avoid any accidental commits, run:

      ```shell
      git update-index --skip-worktree config/vertex_key.json
      ```

  - Generate an SSH key and upload the generated key to your GitHub account.

### Docker

The evaluation challenge projects inside Docker containers.
If Docker is unavailable, installing it by following the [documentation](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository).
Then, enable [managing Docker as a non-root user](https://docs.docker.com/engine/install/linux-postinstall/#manage-docker-as-a-non-root-user).

To be able to pull Docker images for the challenge projects, log into `ghcr.io` using your PAT, run:

  ```shell
  echo "<token>" | docker login ghcr.io -u <user> --password-stdin
  ```

replacing `<user>` and `<token>` with your generated PAT.

## Running the evaluation

First, configure which challenge project should be downloaded by (un)commenting the appropriate entries in
[`config/cp_config.yaml`](./config/cp_config.yaml).

Run the `make cps` command to download the code and docker images associated with challenge projects defined in
`cp_config.yaml`. The code will be downloaded to [cp_root](cp_root).

Finally, run the evaluation using `inspect eval exploit.py --model=<model> -T cp=<challenge project> -S max_iterations=<num>` e.g.

For example:

```shell
inspect eval exploit.py --model=openai/o1 -T cp=nginx-cp-full
```

will run the `mock-cp` project with 8 reflexion loops. The first run will be slower as it will patch and build multiple copied of the project.

## Contributing

### Dependencies

Development dependencies are listed in [`pyproject.toml`](./pyproject.toml).
To install all dependencies for development, run:

```shell
pip install -e .[dev]
```

Dependencies for the evaluation image are defined in [`pyproject.toml`](pyproject.toml).

The project uses [`pip-tools`](https://github.com/jazzband/pip-tools) to manage dependencies.

#### Tooling

The project includes some non-exhaustive type hinting, which is checked through GitHub actions. It is there to help, not
hinder so if it highlights something being wrong, it's likely a potential source of buggy behaviours. You can run it at
any time using `pyright -p src/`. It also includes `isort` and `black` to autoformat your code. You can run these at
any time using `isort src` and `black src`.

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

The interfaces with the various components can be found in [api](src/api).
To interact with the challenge projects, the [api.cp.ChallengeProject](src/api/cp.py) class exposes the relevant
functionality as methods.

For debugging, logger output is provided. By default, only `INFO` and up are printed to the Docker attached tty. The
full logs, including `DEBUG` and logs from underlying libraries such as git commands and network requests to litellm,
are printed to `/crs_scratch/crs.log`.

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
