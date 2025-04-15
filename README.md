# algorand-node-fly

Run your own Algorand node on Fly.io, initialized with a Genesis account with a desired amount of money automatically converted to [XDR](https://en.wikipedia.org/wiki/Special_drawing_rights) and stored with 1 XDR = 1,000,000,000,000 microAlgos.

Prerequisites:

- `git`
- `python3`
- `fly`

Instructions (important: these instructions make you create your completely self-hosted network, unrelated to the Algorand main network):

1. `git clone https://github.com/hermesloom/algorand-node-fly`
2. `cd algorand-node-fly`
3. `local/setup.sh 10000 EUR`
   1. Answer `Would you like to copy its configuration to the new app?` with `y`
   2. Answer `Do you want to tweak these settings before proceeding?` with `n`
   3. Answer `Would you like to allocate dedicated ipv4 and ipv6 addresses now?` with `y`

## License

MIT
