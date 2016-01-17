from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.models import Account
from rest_framework.authtoken.models import Token
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from accounts.serializers import *
from django.core.exceptions import ObjectDoesNotExist
import requests
import json
from rest_framework_swagger import *

class CreateAccount(APIView):
  def post(self, request, format=None):
    """
    Create an account. Returns 201 upon successful creation, and 400 for already
    existing user or for any other bad request.
    ---
    request_serializer: RegistrationSerializer
    response_serializer: RegistrationSerializer
    """
    serializer = RegistrationSerializer(data=request.data)
    if serializer.is_valid():
      try:
        account = Account.objects.get(username=serializer.data['username'])
      except ObjectDoesNotExist:
        account = Account.objects.create_user(
          serializer.data['username'],
          '',
          serializer.data['password']
        )
        token = Token.objects.create(user=account)
        print token
        return Response({'token': token.key}, status=status.HTTP_201_CREATED)
      return Response({'errors': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ScheduleAccount(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def post(self, request, format=None):
    """
    Set an amount of money to save at a set frequency.
    Returns 200 upon success and 400 on error.
    ---
    request_serializer: ScheduleSerializer
    """
    serializer = ScheduleSerializer(data=request.data)
    if serializer.is_valid():
      request.user.scheduled_deposit = serializer.data['amount']
      request.user.scheduled_frequency = serializer.data['frequency']
      request.user.save()
      return Response({'success': True}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AccountInfo(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def get(self, request, format=None):
    """
    Retrieve the account information.
    Returns 200 upon success.
    ---
    response_serializer: AccountSerializer
    """
    return Response(AccountSerializer(request.user).data)

class AccountBalanceInfo(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def get(self, request, format=None):
    """
    Retrieve the account's balance information.
    Returns 200 upon success.
    ---
    response_serializer: BalanceSerializer
    """
    return Response(BalanceSerializer(request.user).data)

class AccountWithdraw(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def post(self, request, format=None):
    """
    Withdraw from the account's savings.
    Returns 200 upon success and 400 on withdrawing amount greater than
    the total savings or for any other bad request.
    ---
    request_serializer: WithdrawSerializer
    """
    serializer = WithdrawSerializer(data=request.data)
    if serializer.is_valid():
      withdrawal = serializer.data['withdrawal']
      if withdrawal > request.user.savings: # withdrawing amount more than savings
        return Response({'errors': 'Withdrawing amount greater than total savings'}, status=status.HTTP_400_BAD_REQUEST)
      request.user.savings = request.user.savings - withdrawal
      request.user.save()
      return Response({'success': True}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AccountDeposit(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def post(self, request, format=None):
    """
    Deposit into the account's savings.
    Returns 200 upon success and 400 on error.
    ---
    request_serializer: DepositSerializer
    """
    serializer = DepositSerializer(data=request.data)
    if serializer.is_valid():
      request.user.savings = request.user.savings + serializer.data['deposit']
      request.user.save()
      return Response({'success': True}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AccountIsActive(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def get(self, request, format=None):
    """
    Query whether or not the account is saving money
    at the specified frequency.
    ---
    response_serializer: IsActiveSerializer
    """
    return Response(IsActiveSerializer(request.user).data)

class AccountRestart(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def get(self, request, format=None):
    """
    Sets the active status of the account to true.
    Returns 200 upon success and 400 if account is already active.
    ---
    response_serializer: ScheduleSerializer
    """
    if request.user.active: #error if already active
      return Response({'errors': 'Already active'}, status=status.HTTP_400_BAD_REQUEST)
    request.user.active = True
    request.user.save()
    return Response({'success': True}, status=status.HTTP_200_OK)

class AccountPause(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def get(self, request, format=None):
    """
    Sets the active status of the account to false.
    Returns 200 upon success and 400 if account is already inactive.
    ---
    response_serializer: ScheduleSerializer
    """
    if not(request.user.active): #error if already active
      return Response({'errors': 'Already not active'}, status=status.HTTP_400_BAD_REQUEST)
    request.user.active = False
    request.user.save()
    return Response({'success': True}, status=status.HTTP_200_OK)

class AccountLink(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def post(self, request, format=None):
    """
    Links the account to the given bank account.
    Returns 200 upon success and 400 on error.
    ---
    request_serializer: BankAccountSerializer
    """
    serializer = BankAccountSerializer(data=request.data)
    if serializer.is_valid():
      payload = {
        'public_key': '67393c180257916a023493c5adc0d3',
        'username': serializer.data['bank_username'],
        'password': serializer.data['bank_password'],
        'institution_type': serializer.data['institution'],
        'product': 'auth',
        'include_accounts': True,
      }
      r = requests.post("https://link-tartan.plaid.com/authenticate", data=payload)
      response = r.json()
      if r.status_code != 200:
        return Response(r.json(), status=status.HTTP_400_BAD_REQUEST)
      else:
        accounts = []
        for account in response['accounts']:
          accounts.append({
            'balance': account['balance']['current'],
            'id': account['_id'],
            'name': account['meta']['name']
          })
        result = {'accounts': accounts, 'token': response['public_token']}
        return Response(json.dumps(result), status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AccountMock(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)



class AccountConfirm(APIView):
  authentication_classes = (TokenAuthentication, SessionAuthentication)
  permission_classes = (IsAuthenticated,)

  def post(self, request, format=None):
    """
    Confirms the given account.
    Returns 200 upon success and 400 on error.
    ---
    request_serializer: BankConfirmSerializer
    """
    serializer = BankConfirmSerializer(data=request.data)
    if serializer.is_valid():
      payload = {
        'client_id': '569ab81ba4ce3935462bb607',
        'secret': '973fdf467c57fc885fbd631a5653bd',
        'public_token': serializer.data['token'],
        'account_id': serializer.data['account_id'],
      }
      r = requests.post("https://tartan.plaid.com/exchange_token", data=payload)
      response = r.json()
      if r.status_code != 200:
        return Response(r.json(), status=status.HTTP_400_BAD_REQUEST)
      else:
        request.user.token = response['stripe_bank_account_token']
        request.user.save()
        return Response({'success': True}, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)