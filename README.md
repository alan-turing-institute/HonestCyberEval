# CRS Sandbox

This repository, the `CRS Sandbox` includes a `./compose.yaml` file.
This file is the only resource competitors will have for infrastructure automation at competition time.
Environment variables and secrets will be injected into the `compose.yaml` from each competitors private copy of the `CRS Sandbox`.

Competitor SSO accounts to GitHub will be limited to a basic set of actions for making modifications and merging PRs within the GitHub repository.

## Evaluation Window

### Phase 1 - GitHub Actions Passing

Date: 2024-05-30
On the above date, teams will be provided access to their private CRS repositories.

This repository will be generated from the CRS Sandbox reference repository which will be treated as the template repository.

Merging into main will require the workflows specified in `.github/workflows/evaluator.yml` and `.github/workflows/package.yml` to pass.

Failure to do so will prevent a team's CRS from moving forward to Phase 2.

### Phase 2 - Automated Execution of your CRS

Date: TBD

On the above date, the AIxCC Game Architecture team will automatically execute competitors CRSs against a subset of published challenge problems.

The CRS MUST be released via [GitHub Release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository) and all GitHub actions must pass.

Competitors must release new versions of their CRS with an updated tag from `main` after the start of Phase 2.

With each new release of a competitors CRS it will be automatically executed.

Only the latest semantic version of a competitors CRS that is properly tagged from `main` will be tested.

## Code Owners

Please review the [.github/CODEOWNERS](.github/CODEOWNERS) file.
This file shows all the files that cannot be modified by competitors.
The `main` branch protections will prevent making changes to these files.

## CRS Constraints on Docker and Virtualization

In the competition environment, a CRS is expected to use Docker (via `run.sh`)
to exercise the CPs that are packaged and configured to be built, tested, and
patched using the provided Docker container.

One CP (the public Linux kernel CP) includes `virtme-ng` in its CP-specific
Docker container for the purposes of testing the built kernel.

This is the only form of nested virtualization or nested containerization that
will be supported by the competition environment. A CRS **MUST NOT** assume that
nested containers or another virtualization/hypervisor technology will be
compatible with the competition environment.

## Environment Variables & GitHub Secrets

Each competitors CRS will come pre-packaged with a list of GitHub secrets and environment variables.
Teams may change the values of these secrets, however they must not change the name of the pre-existing
secrets or variables and must ensure their application code uses the core variables related to the iAPI and LiteLLM connections.

This is so the AIxCC infrastructure team can override the per-competitor secrets and variables at competition time,
yet competitors can use these secrets for connecting to their cloud vendor and/or LLM APIs as needed.

There are currently 4 LLM Provider environment variables declared but not populated in example.env, which will be populated at competition time:

- OPENAI\_API\_KEY
- AZURE\_API\_KEY
- AZURE\_API\_BASE
- GOOGLE_APPLICATION_CREDENTIAL
- ANTHROPIC\_API\_KEY
Note: For local development the example.env file should be renamed to env.

*TBD* - These variables and the LiteLLM configuration file are not yet complete. This will be released in a CRS sandbox update.
We will continue iterating on the CRS sandbox as we grow closer to the competition in order to support newer versions of components.

Please see the competition rules and technical release as the cut off dates for changes will be descibed there.

## LiteLLM Models Supported

| Provider  | Model                  | Pinned Version              |
| --------- | ---------------------- | --------------------------- |
| OpenAI    | gpt-3.5-turbo          | gpt-3.5-turbo-0125          |
| OpenAI    | gpt-4                  | gpt-4-0613                  |
| OpenAI    | gpt-4-turbo            | gpt-4-turbo-2024-04-09      |
| OpenAI    | gpt-4o                 | gpt-4o-2024-05-13           |
| OpenAI    | text-embedding-3-large | text-embedding-3-large      |
| OpenAI    | text-embedding-3-small | text-embedding-3-small      |
| Anthropic | claude-3-sonnet        | claude-3-sonnet-20240229    |
| Anthropic | claude-3-opus          | claude-3-opus-20240229      |
| Anthropic | claude-3-haiku         | claude-3-haiku-20240307     |
| Google    | gemini-pro             | gemini-1.0-pro-002          |
| Google    | gemini-1.5-pro         | gemini-1.5-pro-preview-0514 |
| Google    | textembedding-gecko    | textembedding-gecko@003     |

Note: OpenAI Embedding models have not currently been released in more than a single version, thus pinned/name strings are identical.

All OpenAI models also have an Azure-hosted version that is identical, for load-balancing. Competitors will be able to freely request the
model they like by the Model name in chart above without having to worry about addressing them directly.

Note: Embedding models have not currently been released in more than a single version.

These are utilized by hitting the LiteLLM /chat/completions endpoint, specifying model and message using the OpenAI JSON request format.
Note: Further models will be supported in subsequent iterations.

## Local Development

We recommend using Ubuntu 22.04 LTS for CRS Sandbox development and will be unable to investigate issues with other base operating systems.

### GitHub Personal Access Token (PAT)

In order to work with the CRS Sandbox you must setup your GitHub personal access token or PAT following these steps.

1. Configure a personal access token (PAT) with `read:packages` permission by following this [guide](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic)
2. Authorize the generated PAT for the `aixcc-sc` organization by this [guide](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-a-personal-access-token-for-use-with-saml-single-sign-on)
3. Run `echo "example-token-1234" | docker login ghcr.io -u USERNAME --password-stdin` replacing example-token-1234 with your generated PAT
4. Confirm that you see `> Login Succeeded` in your output from step #3.

### GitHub SSH Key

1. Generate an SSH key by following this [guide](https://docs.github.com/en/enterprise-cloud@latest/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
2. Upload the generated SSH key to your AIxCC GitHub account by following this [guide](https://docs.github.com/en/enterprise-cloud@latest/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account)
3. Follow this [guide](https://docs.github.com/en/enterprise-cloud@latest/authentication/authenticating-with-saml-single-sign-on/authorizing-an-ssh-key-for-use-with-saml-single-sign-on)
to authorize the SSH key for the `aixcc-sc` organization

### Precommit

This repository has a [.pre-commit-config.yaml](.pre-commit-config.yaml) file for assisting with local development.

While competitors are not required to use this, they may find it easier to pass the mandatory evaluation checks.

You can install the command-line tool by going [here](https://pre-commit.com/#install)

### Dependencies

Most dependencies in this repository can be automatically managed by `mise`, but you'll have to install the following yourself:

- docker >= 24.0.5
- docker-compose >= 2.26.1
- GNU make >= 4.3

#### Dependencies managed using mise

This repository defines its dependencies in a [`.tool-versions`](./.tool-versions) file.
[`mise`](https://mise.jdx.dev/getting-started.html#quickstart) can read this file and automatically install the tools at the required versions.
Install `mise`, set it up in your shell, and then run `mise install`.
`mise` will then manage your `PATH` variable to make the tools available whenever you `cd` into this repository.

We've included a Makefile with helpful targets to make working with the CRS Sandbox easier.
However, you can copy any commands and run them on your own.
Please note the use of `--profile` with all `docker compose` commands.
This is so we can easily swap `--profile development` with `--profile competition` at competition time, but competitors can use the `--profile development` to run the local copy of emulated resources.

### Data Sharing & Volumes

A CRS MUST copy CP repositories from `/cp_root` to a writable location such as `/crs_scratch` for building and testing CPs.
A CRS MUST NOT modify data within `/cp_root` directly.
A CRS MUST use `/crs_scratch` as the only shared filesystem between containers.
No other folders or volumes will be shared between containers.

### No internet Access

As stated previously, a CRS will NOT have internet access except for via the LiteLLM proxy to the configured LLM providers.

Because of this competitors MUST provide all artifacts within their Docker container images.

All images needed to execute a CRS MUST be included under `.github/workflows/package.yml` under the `jobs.build-and-push-image.strategy.matrix.include` section.

The Game Architecture team will migrate these images to the competition environment prior to starting your CRS.

### Release Process

We've modified our original guidance on the tagging process.

All teams should be using [SemVer 2.0.0](https://semver.org/) to tag releases.

A team MUST have a tag of `1.0.0` OR greater within their private CRS repository at competition.

Teams MUST NOT use a `v` prefix in their tags.

All releases MUST be from the `main` branch ONLY. Failure to create release tags from `main` will lead to a failed release.

Teams can create these tags by following the GitHub Release process with <https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository>

This will automatically tag any Docker images you've specified under `.github/workflows/package.yml` outlined above.

This will also tag the Helm chart of your CRS automatically.

At competition the AIxCC Game Architecture team will use the latest SemVer tag available on your repository that was present at the end of the submission window.

### Using Make

A Makefile has been provided with a number of a commands to make it easy to clone the exemplar repos, stand up the environment, and a variety of other actions.

Copy `sandbox/example.env` to `sandbox/.env` and replace the variables with your own for local development

```bash
cp sandbox/example.env sandbox/.env
```

`make cps` - clones the exemplar challenges into `./cp_root` folder
`make up` - brings up the development CRS Sandbox, you can visit <http://127.0.0.1:8080/docs> to see the iAPI OpenAPI spec.

The CRS Sandbox currently uses Grafana/K6 as a placeholder for the CRS solution itself and is used to validate that the sandbox can reach the proper HTTP endpoints within the iAPI and LiteLLM containers.

`make down` - tears down the development CRS Sandbox

See [Makefile](./Makefile) for more commands

`make force-reset` - performs a full Docker system prune of all local docker containers, images, networks, and volumes. This can be useful if you accidentally orphaned some docker process or other resources.

### Kubernetes

The Makefile includes endpoints for `make k8s` and `make k8s/competition` which will generate a helm chart in a `./charts/` folder.
The `make k8s` command uses Kind to run Kubernetes locally and will also apply the generated Helm chart onto your cluster.
This process uses a component called [Kompose](https://kompose.io/conversion/) for translating the Docker Compose file into resources.
The CRS Sandbox will include a CI/CD action which the private repos must also use.
This will generate and push the container images to the respective per-competitor private GitHub.
This will also push the Helm chart as an OCI compliant chart to the private GitHub repos.

### Architecture Diagram

This diagram depicts the CRS Sandbox during the `development` phase with `--profile development` and during the `competition` phase with `--profile competition`.
As you can see the iAPI remains as part of the CRS Sanbox but can communicate with the upstream API.
However, the LiteLLM component moves to a centralized component that does NOT run within the CRS Sandbox at competition.

![arch diagram](./architecture.png)
