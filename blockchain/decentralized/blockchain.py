import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request

HOST = "127.0.0.1"
PORT = "5000"
REWARD = 0.25
MASTER_NODE = "127.0.0.1:5000"

class Blockchain:
    def __init__(self):
      self.nodes = set()

      # Add own node to the nodes registry
      self.base_url = f"http://{HOST}:{PORT}/"
      self.register_node(self.base_url)

      if not MASTER_NODE in list(self.nodes):
        # Register instantiated node into master node registry
        nodes = list(self.nodes)
        requests.post(f"http://{MASTER_NODE}/nodes/register", json = {"nodes": nodes})

        # Request current transactions from master node
        response = requests.get(f"http://{MASTER_NODE}/transactions")
        self.current_transactions = response.json()['transactions']

        # Request up to date chain from master node
        response = requests.get(f"http://{MASTER_NODE}/chain")
        self.chain = response.json()['chain']

        # Request the network node registry from master node and register them one by one
        response = requests.get(f"http://{MASTER_NODE}/nodes")
        nodes = response.json()['nodes']
        for node in nodes:
          self.register_node(node)
      
      else:
        self.current_transactions = []
        self.chain = []

        # Create the genesis block
        self.new_block(previous_hash='1', proof=100)
    
    def register_node(self, address):
      """
      Add a new node to the list of nodes

      :param address: Address of node. Eg. 'http://192.168.0.5:5000'
      """

      parsed_url = urlparse(address)
      if parsed_url.netloc:
        address = parsed_url.netloc
      elif parsed_url.path:
        # Accepts an URL without scheme like '192.168.0.5:5000'.
        address = parsed_url.path
      else:
        raise ValueError('Invalid URL')
      
      nodes = list(self.nodes)

      # Register a new node if not found in registry
      if not address in nodes:
        self.nodes.add(address)

        # Broadcast to all nodes the new node added to the registry 
        for node in nodes:
          if node != urlparse(self.base_url).netloc:
            requests.post(f"http://{node}/nodes/register", json = {"nodes": [address]})    
      
    def new_block(self, proof, previous_hash):
      """
      Create a new Block in the Blockchain
      
      :param proof: The proof given by the Proof of Work algorithm
      :param previous_hash: Hash of previous Block
      :return: New Block
      """
      
      block = {
        'index': len(self.chain) + 1,
        'timestamp': time(),
        'transactions': self.current_transactions,
        'proof': proof,
        'previous_hash': previous_hash or self.hash(self.chain[-1])
      }
      
      # Reset the current list of transactions
      self.current_transactions = []

      # Make sure that our chain is the good one
      self.resolve_conflicts_chain

      self.chain.append(block)

      # Broadcast to the other nodes that a block has been added and that current transactions must be reseted
      neighbours = list(self.nodes)
      for node in neighbours:
        if node != urlparse(self.base_url).netloc:
          requests.get(f"http://{node}/nodes/resolve?reset_transactions=1")

      return block

    def new_transaction(self, doer, task, duration):
      """
      Creates a new transaction to go into the next mined Block
      
      :param doer: identificator of the person who carried out the task
      :param task: description of the task done
      :param duration: duration spent in doing the task
      :return: The index of the Block that will hold this transaction
      """
      
      self.current_transactions.append({
            'index': len(self.current_transactions) + 1,
            'doer': doer,
            'task': task,
            'duration': duration,
            'status': 'pending',
            'reviewer': '',
            'timestamp': time()
      })

      # Broadcast transaction list to rest of nodes
      neighbours = list(self.nodes)
      for node in neighbours:
        if node != urlparse(self.base_url).netloc:
          requests.post(f"http://{node}/update_transaction_list", json = {"transactions": self.current_transactions})
      
      return self.last_block['index'] + 1

    def change_transaction_status(self, ix_list, status, reviewer):
      """
      Change the status of a given transaction from the list
      
      :param ix_list: list of transactions indexes which status needs to be changed
      :param status: New status
      :return: The index of the Block that will hold this transaction
      """
      
      current_transactions = self.current_transactions
      reviewed_transactions = 0
      for i in range (0, len(current_transactions)):
        if ((current_transactions[i]['index'] in ix_list) and (current_transactions[i]['doer'] != reviewer) and (current_transactions[i]['status'] != status) and (current_transactions[i]['reviewer'] != reviewer)):
          current_transactions[i]['status'] = status
          reviewed_transactions += 1
          current_transactions[i]['reviewer'] = reviewer
                        
      # In this blockchain, instead of giving credits for the effort of mining, we give credits for the effort of reviewing the transactions
      if reviewed_transactions > 0:
        self.current_transactions.append({
          'index': len(self.current_transactions) + 1,
          'doer': reviewer,
          'status': "accepted",
          'task': "Task list review",
          'duration': reviewed_transactions*REWARD, 
          'timestamp': time()
        })
        
      # If all transactions have been accepted or rejected, mine a new block with all transactions
      required_status = ['accepted', 'rejected']
      count = 0
      for i in range (0, len(current_transactions)):
        if current_transactions[i]['status'] in required_status:
          count = count + 1
      if count == len(current_transactions):
        last_block = self.last_block
        proof = self.proof_of_work(last_block)
        previous_hash = self.hash(last_block)
        block = self.new_block(proof, previous_hash)
      
      # Broadcast transaction list to rest of nodes
      neighbours = list(self.nodes)
      for node in neighbours:
        if node != urlparse(self.base_url).netloc:
          requests.post(f"http://{node}/update_transaction_list", json = {"transactions": self.current_transactions})
             
      return self.last_block['index'] + 1
    
    def reset_transactions(self):
      """
      Reset transactions, for instance, when another node has mined a block
      """

      self.current_transactions = []
    
    def update_transaction_list(self, transactions):
      """
      Override current transactions with the transactions sent from another node.
      :param transactions: list of transactions

      :return: The index of the Block that will hold this transaction
      """

      self.current_transactions = transactions

      return self.last_block['index'] + 1

    @property
    def last_block(self):
      return self.chain[-1]

    @staticmethod
    def hash(block):
      """
      Creates a SHA-256 hash of a Block
      
      :param block: Block
      """
      
      # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
      block_string = json.dumps(block, sort_keys=True).encode()
      return hashlib.sha256(block_string).hexdigest()
    
    def proof_of_work(self, last_block):
      """
      Simple Proof of Work Algorithm:
      
      - Find a number p' such that hash(pp') contains leading 4 zeroes
      - Where p is the previous proof, and p' is the new proof
      
      :param last_block: <dict> last Block
      :return: <int>
      """
      
      last_proof = last_block['proof']
      last_hash = self.hash(last_block)
      
      proof = 0
      while self.valid_proof(last_proof, proof, last_hash) is False:
        proof += 1
        
        return proof
      
    @staticmethod
    def valid_proof(last_proof, proof, last_hash):
      """
      Validates the Proof
        
      :param last_proof: <int> Previous Proof
      :param proof: <int> Current Proof
      :param last_hash: <str> The hash of the Previous Block
      :return: <bool> True if correct, False if not.
      """
        
      guess = f'{last_proof}{proof}{last_hash}'.encode()
      guess_hash = hashlib.sha256(guess).hexdigest()
      return guess_hash[:4] == "0000"

    def valid_chain(self, chain):
      """
      Determine if a given blockchain is valid

      :param chain: A blockchain
      :return: True if valid, False if not
      """

      last_block = chain[0]
      current_index = 1

      while current_index < len(chain):
        block = chain[current_index]
        print(f'{last_block}')
        print(f'{block}')
        print("\n-----------\n")
        # Check that the hash of the block is correct
        last_block_hash = self.hash(last_block)
        if block['previous_hash'] != last_block_hash:
          return False

        # Check that the Proof of Work is correct
        if not self.valid_proof(last_block['proof'], block['proof'], last_block_hash):
          return False

        last_block = block
        current_index += 1

      return True

    def resolve_conflicts_chain(self):
      """
      This is our consensus algorithm, it resolves conflicts
      by replacing our chain with the longest one in the network.

      :return: True if our chain was replaced, False if not
      """
      
      neighbours = list(self.nodes)
      
      new_chain = None

      # We're only looking for chains longer than ours
      max_length = len(self.chain)

      # Grab and verify the chains from all the nodes in our network
      for node in neighbours:
        response = requests.get(f'http://{node}/chain')

        if response.status_code == 200:
          length = response.json()['length']
          chain = response.json()['chain']

          # Check if the length is longer and the chain is valid
          if length > max_length and self.valid_chain(chain):
            max_length = length
            new_chain = chain

      # Replace our chain if we discovered a new, valid chain longer than ours
      if new_chain:
        self.chain = new_chain
        return True

      return False


# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-', '')

# Instantiate the Blockchain
blockchain = Blockchain()
  
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
  values = request.get_json()
  
  # Check that the required fields are in the POST'ed data
  required = ['doer', 'task', 'duration']
  if not all(k in values for k in required):
    return 'Missing values', 400
   
  # Create a new Transaction
  index = blockchain.new_transaction(values['doer'], values['task'], values['duration'])
  
  response = {'message': f'Transaction will be added to Block {index}'}
  return jsonify(response), 201

@app.route('/transactions', methods=['GET'])
def transactions():
  response = {
    'transactions': blockchain.current_transactions,
    'length': len(blockchain.current_transactions),
  }
  return jsonify(response), 200

@app.route('/transactions/status/update', methods=['POST'])
def change_transaction_status():
  values = request.get_json()
  
  # Check that the required fields are in the POST'ed data
  required = ['ix_list', 'status', 'reviewer']
  if not all(k in values for k in required):
    return 'Missing values', 400
  
  required_status = ['accepted', 'rejected', 'pending']
  if not values['status'] in required_status:
    return 'Wrong status value, please only use accepted, rejected or pending', 400
  
  # Change the status of the inputted transactions
  index = blockchain.change_transaction_status(values['ix_list'], values['status'], values['reviewer'])
  response = {
    'transactions': blockchain.current_transactions,
    'length': len(blockchain.current_transactions),
    'message': f'Transaction will be added to Block {index}'
  }
  return jsonify(response), 201  
  
@app.route('/chain', methods=['GET'])
def full_chain():
  response = {
    'chain': blockchain.chain,
    'length': len(blockchain.chain)
  }
  return jsonify(response), 200

@app.route('/nodes', methods=['GET'])
def nodes():
  response = {
    'nodes': list(blockchain.nodes),
    'length': len(list(blockchain.nodes)),
  }
  return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
  values = request.get_json()

  nodes = values.get('nodes')
  if nodes is None:
    return "Error: Please supply a valid list of nodes", 400

  for node in nodes:
    blockchain.register_node(node)

  response = {
    'message': 'New nodes have been added',
    'total_nodes': list(blockchain.nodes),
  }
  return jsonify(response), 201

@app.route('/chain/resolve', methods=['GET'])
def consensus():
  args = request.args
  reset_transactions = args.get("reset_transactions", default=0, type=int)
  replaced = blockchain.resolve_conflicts_chain()

  if replaced:
    response = {
      'message': 'Our chain was replaced',
      'new_chain': blockchain.chain
    }
    if reset_transactions == 1:
      blockchain.reset_transactions()
  else:
    response = {
      'message': 'Our chain is authoritative',
      'chain': blockchain.chain
    }

  return jsonify(response), 200

@app.route('/transactions/update', methods=['POST'])
def update_transaction_list():
  values = request.get_json()
  
  index = blockchain.update_transaction_list(values['transactions'])
  
  response = {
    'transactions': blockchain.current_transactions,
    'length': len(blockchain.current_transactions),
    'message': f'Transaction will be added to Block {index}'
  }
  
  return jsonify(response), 201

if __name__ == '__main__':
  from argparse import ArgumentParser
  
  parser = ArgumentParser()
  parser.add_argument('-p', '--port', default=PORT, type=int, help='port to listen on')
  args = parser.parse_args()
  port = args.port
  
  app.run(host=HOST, port=port)