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

## Future work
- Use Inspect Docker sandbox instead of AIxCC Docker scripts for better integration
- Support challenge projects that expect input as bytes
- More tasks
