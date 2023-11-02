local keymap = vim.api.nvim_set_keymap

local lspconfig = require("lspconfig")
local null_ls = require("null-ls")

local capabilities = require("cmp_nvim_lsp").default_capabilities(vim.lsp.protocol.make_client_capabilities())

lspconfig.pyright.setup({
	on_attach = on_attach,
	capabilities = capabilities,
})

local null_ls = require("null-ls")
local lspconfig = require("lspconfig")
local opts = { noremap = true, silent = true }
local keymap = vim.api.nvim_set_keymap
